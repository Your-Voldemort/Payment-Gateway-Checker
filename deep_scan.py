"""Deep-scan helpers for more powerful gateway detection (Power-ups P1 + P2).

The plain homepage scan misses gateways that only load on checkout/cart/pricing
pages, or that are initialized inside bundled first-party JavaScript. This module
adds two best-effort passes that run against the *same* persistent connection pool:

  * P1 — probe a few likely-payment pages (discovered links first, then blind
    guesses like ``/checkout``) and union any gateways they reveal.
  * P2 — download same-origin ``<script src>`` bundles referenced by the homepage
    and scan their contents (a minified ``app.[hash].js`` that calls ``Stripe(...)``
    is invisible to a static HTML scan).

Everything here is best-effort: failures are swallowed and the homepage result
still stands. Behaviour is bounded by small fetch caps so latency stays low and
the per-host connection pool is reused.
"""
import asyncio
import os
import re
from typing import Awaitable, Callable, List, Optional, Set
from urllib.parse import urljoin, urlparse

import aiohttp

from detection import find_payment_gateways_optimized
from logger import setup_logger

logger = setup_logger()

# --- budgets (env-overridable) -------------------------------------------------
MAX_EXTRA_PAGES = int(os.getenv("DEEP_SCAN_MAX_PAGES", 3))
MAX_SCRIPTS = int(os.getenv("DEEP_SCAN_MAX_SCRIPTS", 3))
PROBE_TIMEOUT = int(os.getenv("DEEP_SCAN_TIMEOUT", 8))
# P3: checkout pages/JS bundles can be large and place the SDK late in the body,
# so use a wider window here than the 512 KB homepage cap.
BYTE_CAP = int(os.getenv("DEEP_SCAN_BYTE_CAP", 1_000_000))
# Only union detections at/above this confidence from secondary pages. Keeps reliable
# SDK/form evidence (>=0.75) and drops noisy low-confidence word mentions (e.g. the word
# "square" on a non-payment /pricing page) that would otherwise inflate false positives.
MIN_CONFIDENCE = float(os.getenv("DEEP_SCAN_MIN_CONFIDENCE", "0.8"))

# Blind path guesses where checkout/payment SDKs commonly load.
CANDIDATE_PATHS = (
    "/checkout", "/cart", "/payment", "/pricing", "/subscribe",
    "/donate", "/shop", "/store", "/plans", "/buy", "/order",
)

# Anchor href/text keywords that hint at a payment-bearing page.
_LINK_KEYWORDS = (
    "checkout", "cart", "payment", "subscribe", "donate",
    "pricing", "plans", "buy", "shop", "store", "order",
)

_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_SKIP_SCHEMES = ("javascript:", "mailto:", "tel:", "data:")
_SCRIPT_SRC_RE = re.compile(r'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _same_origin(base_url: str, candidate: str) -> bool:
    """True if *candidate* (possibly relative) resolves to the same host as base."""
    try:
        b = urlparse(base_url)
        c = urlparse(urljoin(base_url, candidate))
        return bool(c.netloc) and c.netloc == b.netloc and c.scheme in ("http", "https")
    except Exception:
        return False


def discover_payment_links(html: str, base_url: str) -> List[str]:
    """Same-origin links whose href contains a payment-ish keyword (most accurate)."""
    out: List[str] = []
    seen = set()
    for raw in _HREF_RE.findall(html or ""):
        href = raw.strip().split("#", 1)[0]  # drop fragment identifier
        if not href or href.lower().startswith(_SKIP_SCHEMES):
            continue
        low = href.lower()
        if any(k in low for k in _LINK_KEYWORDS) and _same_origin(base_url, href):
            absu = urljoin(base_url, href)
            if absu not in seen:
                seen.add(absu)
                out.append(absu)
    return out


def candidate_page_urls(html: str, base_url: str) -> List[str]:
    """Discovered payment links first, then blind path guesses; deduped, capped."""
    base_norm = base_url.rstrip("/")
    urls = discover_payment_links(html, base_url)
    for path in CANDIDATE_PATHS:
        urls.append(urljoin(base_url, path))

    out: List[str] = []
    seen = set()
    for u in urls:
        if u.rstrip("/") == base_norm:  # don't re-fetch the homepage
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:MAX_EXTRA_PAGES]


def first_party_scripts(html: str, base_url: str) -> List[str]:
    """Same-origin ``<script src>`` URLs from the homepage, deduped and capped."""
    out: List[str] = []
    seen = set()
    for src in _SCRIPT_SRC_RE.findall(html or ""):
        if _same_origin(base_url, src):
            absu = urljoin(base_url, src)
            if absu not in seen:
                seen.add(absu)
                out.append(absu)
    return out[:MAX_SCRIPTS]


async def _fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict,
    cap: int = BYTE_CAP,
    proxy_kwargs: Optional[dict] = None,
) -> Optional[str]:
    """Fetch *url* (status 200 only), streaming up to *cap* bytes. Never raises."""
    try:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT),
            allow_redirects=True,
            **(proxy_kwargs or {}),
        ) as r:
            if r.status != 200:
                return None
            data = bytearray()
            async for chunk in r.content.iter_chunked(32_768):
                data.extend(chunk)
                if len(data) >= cap:
                    del data[cap:]
                    break
            encoding = r.charset or "utf-8"
            return bytes(data).decode(encoding, errors="replace")
    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
        logger.debug(f"deep-scan fetch skipped for {url[:60]}: {e}")
        return None
    except Exception as e:  # noqa: BLE001 — best-effort probe must never break the scan
        logger.debug(f"deep-scan unexpected error for {url[:60]}: {e}")
        return None


async def deep_scan_gateways(
    base_url: str,
    homepage_html: str,
    session: aiohttp.ClientSession,
    headers: dict,
    known_gateways: Optional[List[str]] = None,
    proxy_kwargs: Optional[dict] = None,
    fetcher: Optional[Callable[[str], Awaitable[Optional[str]]]] = None,
) -> Set[str]:
    """Return the union of gateways found across checkout/cart pages (P1) and
    first-party JS bundles (P2), seeded with *known_gateways*. Best-effort.

    Args:
        base_url: The page that was scanned (used to resolve relative URLs).
        homepage_html: Already-fetched homepage HTML to mine for links/scripts.
        session: Shared aiohttp session (reuses the per-host connection pool).
            May be None when *fetcher* is supplied.
        headers: Request headers to reuse (UA + derived client hints).
        known_gateways: Gateways already detected on the homepage.
        proxy_kwargs: aiohttp proxy kwargs for the default fetch path.
        fetcher: optional async ``fetcher(url) -> Optional[str]`` used instead of
            the built-in aiohttp fetch (e.g. a curl_cffi fetcher for flagged domains).

    Returns:
        Set of gateway names (superset of *known_gateways*).
    """
    found: Set[str] = set(known_gateways or [])
    try:
        page_urls = candidate_page_urls(homepage_html, base_url)
        script_urls = first_party_scripts(homepage_html, base_url)
        targets = page_urls + script_urls
        if not targets:
            return found

        logger.info(
            f"Deep scan for {base_url[:60]}: probing {len(page_urls)} page(s) "
            f"and {len(script_urls)} script(s)"
        )

        if fetcher is not None:
            coros = [fetcher(u) for u in targets]
        else:
            coros = [_fetch_text(session, u, headers, BYTE_CAP, proxy_kwargs) for u in targets]
        texts = await asyncio.gather(*coros, return_exceptions=True)
        for t in texts:
            if isinstance(t, str) and t:
                names, matches = find_payment_gateways_optimized(t)
                for name in names:
                    match = matches.get(name)
                    if match is not None and match.confidence >= MIN_CONFIDENCE:
                        found.add(name)
    except Exception as e:  # noqa: BLE001 — never let the deep scan break check_url
        logger.debug(f"deep_scan_gateways error for {base_url[:60]}: {e}")
    return found
