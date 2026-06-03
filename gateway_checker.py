"""Payment gateway checking functionality with optimized detection, retry logic, and result caching."""

import aiohttp
import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple, List, Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from config import Config
from utils import is_valid_url
from detection import (
    analyze_url_response,
    detect_ecommerce_platform,
    detect_cart_abandonment_tools,
)
from user_agents import get_random_user_agent
from cache_manager import get_cached_result, save_to_cache
from http_client import get_http_session
from deep_scan import deep_scan_gateways
from logger import setup_logger

logger = setup_logger()

# Try to import curl_cffi for TLS fingerprint bypass (handles CDN/WAF that use JA3 fingerprinting)
try:
    from curl_cffi import requests as curl_requests

    CURL_CFFI_AVAILABLE = True
    logger.info("curl_cffi available for TLS fingerprint bypass")
except ImportError:
    CURL_CFFI_AVAILABLE = False
    logger.warning(
        "curl_cffi not installed - some CDNs may block requests (pip install curl_cffi)"
    )

# Thread pool for running sync curl_cffi in async context
_curl_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="curl_cffi_")

# Retry configuration for transient failures
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
RETRY_BACKOFF = 2  # exponential backoff multiplier

# Response streaming cap — payment SDKs always live in <head> / early <body>.
# 512 KB is more than enough to capture them while preventing OOM on multi-MB
# pages (news articles, documentation, etc.).
MAX_RESPONSE_BYTES = 512_000  # 500 KB

def _client_hints_for_ua(user_agent: str) -> Dict[str, str]:
    """Build Sec-CH-UA client-hint headers consistent with the chosen User-Agent.

    Only Chromium-based browsers emit these headers. For Firefox/Safari we return
    an empty dict so the fingerprint stays internally consistent — a random Firefox
    UA paired with hardcoded Chrome hints is exactly the mismatch modern WAFs
    (Cloudflare, Akamai, Datadome) flag, which can *reduce* the bypass rate.
    """
    ua = user_agent or ""
    # Firefox and Safari do not send Sec-CH-UA headers; only Chromium does.
    if "Chrome/" not in ua or "Firefox" in ua:
        return {}

    # Major Chromium version, e.g. "Chrome/131.0.0.0" -> "131"
    start = ua.find("Chrome/") + len("Chrome/")
    i = start
    while i < len(ua) and ua[i].isdigit():
        i += 1
    version = ua[start:i] or "120"

    # Platform token derived from the UA string.
    if "Windows" in ua:
        platform = "Windows"
    elif "Android" in ua:
        platform = "Android"
    elif "CrOS" in ua:
        platform = "Chrome OS"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        platform = "macOS"
    elif "Linux" in ua:
        platform = "Linux"
    else:
        platform = "Windows"

    mobile = "?1" if ("Mobile" in ua or "Android" in ua) else "?0"

    return {
        "Sec-Ch-Ua": f'"Not_A Brand";v="8", "Chromium";v="{version}", "Google Chrome";v="{version}"',
        "Sec-Ch-Ua-Mobile": mobile,
        "Sec-Ch-Ua-Platform": f'"{platform}"',
    }


# =============================================================================
# CIRCUIT BREAKER — per-domain failure isolation
# =============================================================================

class CircuitState(Enum):
    """States for the circuit breaker state machine."""
    CLOSED = "closed"        # Normal operation — requests flow through
    OPEN = "open"            # Domain is dead — requests are blocked immediately
    HALF_OPEN = "half_open"  # Cooldown elapsed — one probe request allowed


# Circuit breaker configuration
CB_FAILURE_THRESHOLD = 3    # consecutive failures before tripping OPEN
CB_COOLDOWN_SECONDS  = 300  # 5 minutes before moving to HALF_OPEN
CB_SUCCESS_THRESHOLD = 1    # successes in HALF_OPEN to close the circuit


@dataclass
class _DomainBreaker:
    """
    Per-domain circuit breaker state.

    Tracks consecutive failure counts and timestamps to implement the
    CLOSED → OPEN → HALF_OPEN → CLOSED state machine.
    """
    domain: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    half_open_successes: int = 0
    opened_at: float = 0.0        # monotonic timestamp when tripped OPEN
    last_failure_at: float = 0.0  # monotonic timestamp of last failure

    def is_open(self) -> bool:
        """Check if circuit is blocking requests right now."""
        if self.state == CircuitState.OPEN:
            # Transition to HALF_OPEN once cooldown has elapsed
            if time.monotonic() - self.opened_at >= CB_COOLDOWN_SECONDS:
                self.state = CircuitState.HALF_OPEN
                self.half_open_successes = 0
                return False  # Allow the probe request
            return True  # Still within cooldown — block
        return False  # CLOSED or HALF_OPEN

    def record_success(self) -> None:
        """Record a successful request; close the circuit if thresholds are met."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= CB_SUCCESS_THRESHOLD:
                self.state = CircuitState.CLOSED
                self.consecutive_failures = 0
                self.half_open_successes = 0
        elif self.state == CircuitState.CLOSED:
            # Reset consecutive counter on any success
            self.consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed request; open the circuit if threshold is reached."""
        self.last_failure_at = time.monotonic()
        if self.state == CircuitState.HALF_OPEN:
            # Probe failed — immediately reopen
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            return
        self.consecutive_failures += 1
        if self.consecutive_failures >= CB_FAILURE_THRESHOLD:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()

    def cooldown_remaining(self) -> float:
        """Seconds until the circuit transitions to HALF_OPEN (0 if already there)."""
        if self.state != CircuitState.OPEN:
            return 0.0
        elapsed = time.monotonic() - self.opened_at
        return max(0.0, CB_COOLDOWN_SECONDS - elapsed)


class _CircuitBreakerRegistry:
    """
    Thread/async-safe registry of per-domain circuit breakers.

    Uses a single asyncio.Lock to protect concurrent access from multiple
    bulk-scan tasks running in the same event loop.
    """

    def __init__(self) -> None:
        self._breakers: Dict[str, _DomainBreaker] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        """Lazy-initialise the lock inside an active event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @staticmethod
    def _domain(url: str) -> str:
        """Extract the netloc (host + port) from a URL as the circuit key."""
        parsed = urlparse(url)
        return parsed.netloc.lower() or url.lower()

    async def is_open(self, url: str) -> Tuple[bool, float]:
        """
        Check whether the circuit for this URL's domain is currently OPEN.

        Args:
            url: Full URL being requested

        Returns:
            (is_blocked, cooldown_remaining_seconds)
        """
        domain = self._domain(url)
        async with self._get_lock():
            breaker = self._breakers.get(domain)
            if breaker is None:
                return False, 0.0
            blocked = breaker.is_open()
            remaining = breaker.cooldown_remaining() if blocked else 0.0
            return blocked, remaining

    async def record_success(self, url: str) -> None:
        """Notify the registry that a request to this URL's domain succeeded."""
        domain = self._domain(url)
        async with self._get_lock():
            if domain in self._breakers:
                self._breakers[domain].record_success()

    async def record_failure(self, url: str) -> None:
        """
        Notify the registry that a request to this URL's domain failed.

        Creates a new breaker entry for the domain if one does not exist yet.
        """
        domain = self._domain(url)
        async with self._get_lock():
            if domain not in self._breakers:
                self._breakers[domain] = _DomainBreaker(domain=domain)
            breaker = self._breakers[domain]
            breaker.record_failure()
            if breaker.state == CircuitState.OPEN:
                logger.warning(
                    f"Circuit OPENED for {domain} after "
                    f"{breaker.consecutive_failures} consecutive failures. "
                    f"Domain blocked for {CB_COOLDOWN_SECONDS}s."
                )

    async def reset(self, url: str) -> None:
        """Manually reset the circuit for a domain (owner admin use)."""
        domain = self._domain(url)
        async with self._get_lock():
            self._breakers.pop(domain, None)

    async def get_stats(self) -> Dict[str, dict]:
        """
        Return a snapshot of all circuit breaker states for monitoring.

        Returns:
            Dict mapping domain -> state info dict
        """
        async with self._get_lock():
            return {
                domain: {
                    "state": b.state.value,
                    "consecutive_failures": b.consecutive_failures,
                    "cooldown_remaining": round(b.cooldown_remaining()),
                }
                for domain, b in self._breakers.items()
            }


# Module-level singleton — shared across all check_url() calls
_circuit_breaker = _CircuitBreakerRegistry()


async def get_circuit_breaker_stats() -> Dict[str, dict]:
    """
    Public accessor for circuit breaker stats (used by /cbstats bot command).

    Returns:
        Dict mapping domain -> {state, consecutive_failures, cooldown_remaining}
    """
    return await _circuit_breaker.get_stats()


async def _stream_response_text(
    response: aiohttp.ClientResponse,
    cap: int = MAX_RESPONSE_BYTES,
) -> str:
    """
    Stream an aiohttp response body up to *cap* bytes, then decode to str.

    Instead of loading the entire page into memory with ``response.text()``,
    this reads chunks until either the response is exhausted or the cap is
    reached.  Payment gateway SDKs and checkout widgets always appear in the
    ``<head>`` or early ``<body>``, so 500 KB is sufficient for detection
    while protecting against multi-megabyte pages.

    Args:
        response: An open ``aiohttp.ClientResponse`` inside its context manager.
        cap: Maximum bytes to read (default: ``MAX_RESPONSE_BYTES``).

    Returns:
        Decoded HTML string (may be truncated).
    """
    chunks: list[bytes] = []
    total = 0
    truncated = False

    async for chunk in response.content.iter_chunked(32_768):  # 32 KB read window
        remaining = cap - total
        if len(chunk) >= remaining:
            chunks.append(chunk[:remaining])
            total += remaining
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)

    if truncated:
        url_hint = str(response.url)[:60]
        logger.warning(
            f"Response body capped at {cap // 1024} KB for {url_hint} "
            f"— page may be larger but detection only needs the early HTML."
        )

    raw = b"".join(chunks)
    encoding = response.charset or "utf-8"
    return raw.decode(encoding, errors="replace")


def _fetch_with_curl_cffi(
    url: str, timeout: int = 15, proxy: Optional[str] = None
) -> Tuple[str, int, dict]:
    """
    Fetch URL using curl_cffi with browser impersonation (TLS/JA3/HTTP2 + header order).

    Bypasses TLS/JA3 fingerprinting used by CDNs like Fastly, Cloudflare, Akamai.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        proxy: Optional proxy URL (http/https/socks5, may embed user:pass)

    Returns:
        Tuple of (html_content, status_code, headers_dict)

    Raises:
        Exception on network/request errors
    """
    if not CURL_CFFI_AVAILABLE:
        raise RuntimeError("curl_cffi not available")

    kwargs = {
        "impersonate": _pick_impersonate(),  # browser TLS profile (rotatable)
        "timeout": timeout,
        "allow_redirects": True,
    }
    if proxy:
        kwargs["proxy"] = proxy

    response = curl_requests.get(url, **kwargs)
    return response.text, response.status_code, dict(response.headers)


async def _async_fetch_with_curl_cffi(
    url: str, timeout: int = 15, proxy: Optional[str] = None
) -> Tuple[str, int, dict]:
    """
    Async wrapper for curl_cffi fetch (runs in thread pool).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _curl_executor, _fetch_with_curl_cffi, url, timeout, proxy
    )


# Markers that indicate an anti-bot interstitial rather than the real page.
_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "cf-browser-verification",
    "__cf_chl",
    "cf_chl_opt",
    "challenge-platform",
    "enable javascript and cookies to continue",
    "ddos-guard",
    "px-captcha",
    "_imperva_",
    "incapsula incident",
    "datadome",
)

# Domains that tripped anti-bot defenses on the plain client; fetch via curl_cffi first.
_force_curl_domains: set = set()


def _pick_proxy() -> Optional[str]:
    """Choose a proxy URL: rotate over PROXY_LIST, else PROXY_URL, else None."""
    if Config.PROXY_LIST:
        return random.choice(Config.PROXY_LIST)
    return Config.PROXY_URL or None


def _aiohttp_proxy_kwargs(proxy: Optional[str]) -> dict:
    """Translate a proxy URL into aiohttp get() kwargs, splitting out basic auth."""
    if not proxy:
        return {}
    parsed = urlparse(proxy)
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        netloc = f"{host}:{parsed.port}" if parsed.port else host
        clean = parsed._replace(netloc=netloc).geturl()
        return {
            "proxy": clean,
            "proxy_auth": aiohttp.BasicAuth(parsed.username or "", parsed.password or ""),
        }
    return {"proxy": proxy}


def _pick_impersonate() -> str:
    """Pick a curl_cffi impersonation target (rotates if CURL_IMPERSONATE is a list)."""
    choices = [c.strip() for c in str(Config.CURL_IMPERSONATE).split(",") if c.strip()]
    return random.choice(choices) if choices else "chrome"


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _should_curl_first(url: str) -> bool:
    """True if this domain previously tripped anti-bot defenses (use curl_cffi first)."""
    return (
        CURL_CFFI_AVAILABLE
        and Config.CURL_CFFI_ON_BLOCK
        and _domain_of(url) in _force_curl_domains
    )


def _mark_curl_domain(url: str) -> None:
    domain = _domain_of(url)
    if domain:
        _force_curl_domains.add(domain)


def _looks_like_block(status: int, html: str, headers: dict) -> bool:
    """Heuristic: does this response look like an anti-bot block/challenge rather than
    the real page? Catches 403/429 and 200-with-JS-challenge interstitials."""
    if status in (403, 429):
        return True
    hdr = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    if hdr.get("cf-mitigated") == "challenge":
        return True
    server = hdr.get("server", "")
    if status == 503 and ("cloudflare" in server or "ddos-guard" in server):
        return True
    if not html:
        return False
    low = html[:20000].lower()
    return any(marker in low for marker in _CHALLENGE_MARKERS)


def _make_curl_fetcher(proxy: Optional[str]):
    """Build an async fetcher(url) -> Optional[str] using curl_cffi (+ proxy), so the
    deep scan's sub-fetches go through the hardened path on flagged domains."""
    async def _fetch(target_url: str) -> Optional[str]:
        try:
            text, status, hdrs = await _async_fetch_with_curl_cffi(
                target_url, timeout=Config.REQUEST_TIMEOUT, proxy=proxy
            )
        except Exception:
            return None
        if status != 200 or _looks_like_block(status, text, hdrs):
            return None
        raw = text.encode("utf-8", errors="replace")
        if len(raw) > MAX_RESPONSE_BYTES:
            text = raw[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")
        return text
    return _fetch


async def _curl_cffi_attempt(url: str, use_cache: bool):
    """Fetch via curl_cffi (browser TLS impersonation, optional proxy), analyze, cache.

    Returns the standard 9-tuple on a genuine 200, or None if curl_cffi is unavailable,
    errored, returned non-200, or returned another challenge page. Also runs the deep
    scan (P1/P2) through curl_cffi so hard domains keep checkout/JS coverage.
    """
    if not CURL_CFFI_AVAILABLE:
        return None
    proxy = _pick_proxy()
    try:
        text, curl_status, curl_headers = await _async_fetch_with_curl_cffi(
            url, timeout=Config.REQUEST_TIMEOUT, proxy=proxy
        )
    except Exception as curl_err:
        logger.error(f"curl_cffi failed for {url}: {curl_err}")
        return None

    raw = text.encode("utf-8", errors="replace")
    if len(raw) > MAX_RESPONSE_BYTES:
        text = raw[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")

    if curl_status != 200:
        logger.warning(f"curl_cffi got status {curl_status} for {url}")
        return None
    if _looks_like_block(curl_status, text, curl_headers):
        logger.warning(f"curl_cffi response still looks like a challenge for {url}")
        return None

    logger.info(
        f"curl_cffi succeeded for {url} - bypassed TLS fingerprinting"
        + (" (via proxy)" if proxy else "")
    )

    analysis = analyze_url_response(html=text, headers=curl_headers, status_code=curl_status)
    platform_detection = detect_ecommerce_platform(html=text, headers=curl_headers)
    platform_name = platform_detection["platform"] or "None detected"
    cart_abandonment = detect_cart_abandonment_tools(html=text, headers=curl_headers)
    cart_summary = cart_abandonment["summary"]

    # Deep scan (P1/P2) over curl_cffi so flagged domains keep checkout/JS coverage.
    if Config.DEEP_SCAN_ENABLED:
        try:
            merged = await deep_scan_gateways(
                base_url=url,
                homepage_html=text,
                session=None,
                headers={},
                known_gateways=analysis["gateways"],
                fetcher=_make_curl_fetcher(proxy),
            )
            new_found = [g for g in merged if g not in analysis["gateways"]]
            if new_found:
                analysis["gateways"] = list(analysis["gateways"]) + new_found
                logger.info(f"Deep scan (curl) added {len(new_found)} gateway(s) for {url}")
        except Exception as deep_err:
            logger.debug(f"curl deep scan failed for {url}: {deep_err}")

    await _circuit_breaker.record_success(url)
    if use_cache:
        await save_to_cache(url, {
            "gateways": analysis["gateways"],
            "status_code": curl_status,
            "captcha": analysis["captcha"],
            "cloudflare": analysis["cloudflare"],
            "security_type": analysis["security_type"],
            "cvv_status": analysis["cvv_status"],
            "inbuilt_status": analysis["inbuilt_status"],
            "ecommerce_platform": platform_name,
            "cart_abandonment": cart_summary,
        })

    return (
        analysis["gateways"],
        curl_status,
        analysis["captcha"],
        analysis["cloudflare"],
        analysis["security_type"],
        analysis["cvv_status"],
        analysis["inbuilt_status"],
        platform_name,
        cart_summary,
    )


async def check_url(
    url: str,
    session: Optional[aiohttp.ClientSession] = None,
    retry_count: int = 0,
    use_cache: bool = True,
) -> Tuple[List[str], int, bool, bool, str, str, str, str, str]:
    """
    Check the provided URL for payment gateways, security features, e-commerce platform, and cart abandonment tools.
    Includes automatic retry logic for transient failures (5xx errors, timeouts, connection errors).
    Supports result caching to reduce duplicate checks.
    Integrates per-domain circuit breaker to skip known-dead domains immediately.

    Args:
        url: The URL to check
        session: Optional aiohttp ClientSession for connection reuse
        retry_count: Current retry attempt (internal use, starts at 0)
        use_cache: Whether to use cached results (default: True)

    Returns:
        Tuple containing:
            - List of detected payment gateways
            - HTTP status code
            - Captcha detected (bool)
            - Cloudflare detected (bool)
            - Payment security type description
            - CVV/CVC requirement status
            - Inbuilt payment system status
            - E-commerce platform name (or "None detected")
            - Cart abandonment tools summary (or "None detected")
    """
    if not is_valid_url(url):
        logger.warning(f"Invalid URL provided: {url}")
        return (
            [],
            400,
            False,
            False,
            "Invalid URL",
            "N/A",
            "N/A",
            "None detected",
            "None detected",
        )

    # -------------------------------------------------------------------------
    # Circuit breaker check — skip domains that have been repeatedly failing.
    # Only checked on the first attempt (retry_count == 0) to avoid blocking
    # the retry logic that is already handling a live request sequence.
    # -------------------------------------------------------------------------
    if retry_count == 0:
        is_blocked, cooldown_remaining = await _circuit_breaker.is_open(url)
        if is_blocked:
            domain = urlparse(url).netloc or url
            logger.warning(
                f"Circuit OPEN for {domain} — skipping request "
                f"({int(cooldown_remaining)}s cooldown remaining)"
            )
            return (
                [],
                503,
                False,
                False,
                f"Circuit Open: domain unreachable (retry in {int(cooldown_remaining)}s)",
                "N/A",
                "N/A",
                "None detected",
                "None detected",
            )

    # Check cache first (now checks on retry attempts too for performance)
    if use_cache:
        cached = await get_cached_result(url)
        if cached:
            logger.info(f"Cache hit for {url[:50]} (attempt {retry_count + 1})")
            return (
                cached.get("gateways", []),
                cached.get("status_code", 200),
                cached.get("captcha", False),
                cached.get("cloudflare", False),
                cached.get("security_type", "Unknown"),
                cached.get("cvv_status", "N/A"),
                cached.get("inbuilt_status", "N/A"),
                cached.get("ecommerce_platform", "None detected"),
                cached.get("cart_abandonment", "None detected"),
            )

    # Use rotating user agent to minimize rate limiting
    user_agent = get_random_user_agent()

    # Browser-like headers to bypass WAF/CDN bot detection
    # Modern CDNs (Fastly, Cloudflare, Akamai) use TLS fingerprinting and header analysis
    # Adding Sec-Fetch-* headers and other modern browser headers reduces 400/403 errors
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        # Modern browser security headers (Sec-Fetch-* are sent by all modern browsers)
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        # Additional headers for better compatibility
        "Cache-Control": "max-age=0",
        "DNT": "1",  # Do Not Track
    }
    # P4: client hints derived from the chosen UA (empty for non-Chromium) so the
    # fingerprint is internally consistent and not flagged by WAFs.
    headers.update(_client_hints_for_ua(user_agent))

    # Use the shared persistent connection pool if no session is passed.
    # Previously this created a fresh aiohttp.ClientSession() (and a new TCP
    # pool) on every call, leaking connections.  Now we always default to the
    # module-level singleton from http_client.py.
    close_session = False
    if session is None:
        session = await get_http_session()  # Shared pool — never close this
        close_session = False

    # If this domain previously tripped anti-bot defenses, skip straight to the
    # browser-impersonation client (optionally via proxy) before the plain client.
    if retry_count == 0 and _should_curl_first(url):
        logger.info(f"Domain flagged for curl_cffi-first fetch: {url}")
        _curl_first = await _curl_cffi_attempt(url, use_cache)
        if _curl_first is not None:
            return _curl_first

    try:
        attempt_info = (
            f" (attempt {retry_count + 1}/{MAX_RETRIES + 1})" if retry_count > 0 else ""
        )
        logger.info(f"Checking URL: {url}{attempt_info}")

        # Add small delay to appear more human-like and reduce bot detection
        await asyncio.sleep(0.3)

        timeout = aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT)
        _proxy = _pick_proxy()
        async with session.get(
            url, headers=headers, timeout=timeout, allow_redirects=True,
            **_aiohttp_proxy_kwargs(_proxy)
        ) as response:
            response.raise_for_status()
            # Stream up to MAX_RESPONSE_BYTES to avoid OOM on large pages.
            # Detection targets (<head>, early <body>) are always in the first 500 KB.
            text = await _stream_response_text(response)

            # Anti-bot interstitial returned with a 2xx? Retry via browser impersonation.
            if Config.CURL_CFFI_ON_BLOCK and _looks_like_block(
                response.status, text, dict(response.headers)
            ):
                logger.warning(
                    f"Challenge/block page detected for {url} (status {response.status}) "
                    f"- retrying via curl_cffi"
                )
                _mark_curl_domain(url)
                _bypass = await _curl_cffi_attempt(url, use_cache)
                if _bypass is not None:
                    return _bypass

            # Use the new optimized detection module
            # This provides word-boundary matching, SDK detection, and header analysis
            analysis = analyze_url_response(
                html=text, headers=dict(response.headers), status_code=response.status
            )

            # Detect e-commerce platform
            platform_detection = detect_ecommerce_platform(
                html=text, headers=dict(response.headers)
            )

            # Get platform name or "None detected"
            platform_name = (
                platform_detection["platform"]
                if platform_detection["platform"]
                else "None detected"
            )

            # Log platform detection
            if platform_detection["platform"]:
                logger.info(
                    f"Detected e-commerce platform for {url}: {platform_name} "
                    f"(confidence: {platform_detection['confidence']:.0%})"
                )

            # Detect cart abandonment tools
            cart_abandonment = detect_cart_abandonment_tools(
                html=text, headers=dict(response.headers)
            )

            # Get cart abandonment summary
            cart_summary = cart_abandonment["summary"]

            # Log cart abandonment detection
            if cart_abandonment["tools"]:
                logger.info(
                    f"Detected cart abandonment tools for {url}: {cart_summary}"
                )

            # P1/P2: deep scan — probe checkout/cart pages and first-party JS
            # bundles for gateways that don't surface on the homepage. Best-effort
            # and additive: the union only adds gateways, never drops homepage hits.
            if Config.DEEP_SCAN_ENABLED and response.status == 200 and text:
                _merged = await deep_scan_gateways(
                    base_url=str(response.url),
                    homepage_html=text,
                    session=session,
                    headers=headers,
                    known_gateways=analysis["gateways"],
                    proxy_kwargs=_aiohttp_proxy_kwargs(_proxy),
                    fetcher=_make_curl_fetcher(_proxy) if _should_curl_first(url) else None,
                )
                _new = [g for g in _merged if g not in analysis["gateways"]]
                if _new:
                    analysis["gateways"] = list(analysis["gateways"]) + _new
                    logger.info(
                        f"Deep scan added {len(_new)} gateway(s) for {url}: "
                        f"{', '.join(_new)}"
                    )

            logger.info(
                f"Successfully checked {url} - Status: {response.status}, "
                f"Gateways: {len(analysis['gateways'])} "
                f"(High confidence: {len(analysis['high_confidence_gateways'])})"
            )

            # Successful response — reset circuit breaker for this domain
            await _circuit_breaker.record_success(url)

            # Cache the result if successful (status 200) and caching is enabled
            if use_cache and response.status == 200:
                cache_data = {
                    "gateways": analysis["gateways"],
                    "status_code": response.status,
                    "captcha": analysis["captcha"],
                    "cloudflare": analysis["cloudflare"],
                    "security_type": analysis["security_type"],
                    "cvv_status": analysis["cvv_status"],
                    "inbuilt_status": analysis["inbuilt_status"],
                    "ecommerce_platform": platform_name,
                    "cart_abandonment": cart_summary,
                }
                await save_to_cache(url, cache_data)

            return (
                analysis["gateways"],
                response.status,
                analysis["captcha"],
                analysis["cloudflare"],
                analysis["security_type"],
                analysis["cvv_status"],
                analysis["inbuilt_status"],
                platform_name,
                cart_summary,
            )

    except aiohttp.ClientResponseError as http_err:
        status_code = http_err.status

        # Don't retry client errors (4xx) - these are permanent
        if 400 <= status_code < 500:
            logger.error(f"HTTP client error for {url}: {status_code}")
            # Anti-bot block (403/429): try the browser-impersonation client first.
            if status_code in (403, 429) and Config.CURL_CFFI_ON_BLOCK and CURL_CFFI_AVAILABLE:
                _mark_curl_domain(url)
                logger.warning(
                    f"{status_code} for {url} - trying curl_cffi (browser TLS impersonation)"
                )
                _bypass = await _curl_cffi_attempt(url, use_cache)
                if _bypass is not None:
                    return _bypass
            if status_code == 403:
                logger.warning(
                    f"Access Denied (403) for {url} - server is blocking bot requests. "
                    f"Site may have WAF/anti-bot protection. "
                    f"Attempted with enhanced headers and delays."
                )
                return (
                    [],
                    403,
                    False,
                    False,
                    "403 Forbidden: Access Denied",
                    "N/A",
                    "N/A",
                    "None detected",
                    "None detected",
                )
            elif status_code == 400:
                # Phase 3: For 400 errors, try multiple fallback strategies
                if retry_count == 0:
                    # First fallback: retry with fresh session
                    logger.warning(
                        f"Bad Request (400) for {url} - retrying with fresh session..."
                    )
                    await asyncio.sleep(0.5)
                    return await check_url(url, None, retry_count + 1, use_cache)

                elif retry_count == 1:
                    # Second fallback: browser TLS impersonation (JA3/HTTP2) via curl_cffi
                    _mark_curl_domain(url)
                    logger.warning(
                        f"Bad Request (400) for {url} - retrying with curl_cffi (browser TLS)..."
                    )
                    _bypass = await _curl_cffi_attempt(url, use_cache)
                    if _bypass is not None:
                        return _bypass

                logger.warning(
                    f"Bad Request (400) for {url} - server rejected request format. "
                    f"Possible causes: CDN/WAF blocking, server requires authentication, "
                    f"or API key needed."
                )
                return (
                    [],
                    400,
                    False,
                    False,
                    "HTTP Error: 400 Bad Request",
                    "N/A",
                    "N/A",
                    "None detected",
                    "None detected",
                )
            else:
                return (
                    [],
                    status_code,
                    False,
                    False,
                    f"HTTP Error: {status_code}",
                    "N/A",
                    "N/A",
                    "None detected",
                    "None detected",
                )

        # Retry server errors (5xx) - these are often transient
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAY * (RETRY_BACKOFF**retry_count)
            logger.warning(
                f"Server error {status_code} for {url}, retrying in {delay}s..."
            )
            await asyncio.sleep(delay)
            return await check_url(url, session, retry_count + 1, use_cache)

        # All retries exhausted for 5xx — count as a circuit-breaker failure
        await _circuit_breaker.record_failure(url)
        logger.error(f"HTTP error for {url} after {MAX_RETRIES} retries: {status_code}")
        return (
            [],
            status_code,
            False,
            False,
            f"HTTP Error: {status_code}",
            "N/A",
            "N/A",
            "None detected",
            "None detected",
        )

    except asyncio.TimeoutError:  # covers total, sock_read, sock_connect, and ServerTimeoutError (subclass)
        # Retry timeouts - could be temporary network congestion
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAY * (RETRY_BACKOFF**retry_count)
            logger.warning(f"Timeout for {url}, retrying in {delay}s...")
            await asyncio.sleep(delay)
            return await check_url(url, session, retry_count + 1, use_cache)

        # All retries exhausted on timeout — count as a circuit-breaker failure
        await _circuit_breaker.record_failure(url)
        logger.error(f"Timeout for {url} after {MAX_RETRIES} retries")
        return (
            [],
            408,
            False,
            False,
            "Request Timeout",
            "N/A",
            "N/A",
            "None detected",
            "None detected",
        )

    except aiohttp.ClientConnectionError as conn_err:
        # Retry connection errors - network issues are often temporary
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAY * (RETRY_BACKOFF**retry_count)
            logger.warning(f"Connection error for {url}, retrying in {delay}s...")
            await asyncio.sleep(delay)
            return await check_url(url, session, retry_count + 1, use_cache)

        # All retries exhausted on connection error — trip the circuit breaker
        await _circuit_breaker.record_failure(url)
        logger.error(
            f"Connection error for {url} after {MAX_RETRIES} retries: {str(conn_err)}"
        )
        return (
            [],
            503,
            False,
            False,
            "Connection Error",
            "N/A",
            "N/A",
            "None detected",
            "None detected",
        )

    except Exception as e:
        logger.error(f"Unexpected error checking {url}: {str(e)}")
        return (
            [],
            500,
            False,
            False,
            f"Error: {str(e)}",
            "N/A",
            "N/A",
            "None detected",
            "None detected",
        )

    finally:
        # close_session is always False now — we use the shared http_client.py
        # singleton and must never close it.  Guard kept for safety.
        if close_session:
            await session.close()
