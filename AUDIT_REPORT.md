# Gateway Checker — Bug Audit & Power-Up Report

**Date:** 2026-06-02
**Scope:** Search for breaking code / bugs, and identify how to make gateway detection more powerful.
**Method:** Static trace of the full request → detect → format pipeline
(`bot_aiogram.py` → `gateway_checker.check_url()` → `detection.analyze_url_response()`
→ `html_parser` / `pattern_matcher`), plus `http_client`, `cache_manager`, `utils`.
The headline bug was verified against the official aiohttp documentation.

> **No source files were modified.** Every "Fix" below is a proposal with the exact
> change to apply. Severity legend: 🔴 high · 🟠 medium · 🟡 low · ⚪ cleanup.

---

## Table of contents
- [Bug 1 — Total timeout is silently mishandled](#bug-1--total-timeout-is-silently-mishandled-)
- [Bug 2 — Aho-Corasick matcher is dead code](#bug-2--aho-corasick-matcher-is-dead-code-)
- [Bug 3 — Duplicate URLs in a batch lose results](#bug-3--duplicate-urls-in-a-batch-lose-results-)
- [Bug 4 — Progress branch has no exception guard](#bug-4--progress-branch-has-no-exception-guard-)
- [Bug 5 — Dead legacy detectors in utils.py](#bug-5--dead-legacy-detectors-in-utilspy-)
- [Power-ups — making detection more powerful](#power-ups--making-detection-more-powerful)
- [Prioritized roadmap](#prioritized-roadmap)

---

## Bug 1 — Total timeout is silently mishandled 🔴

**Location:** `gateway_checker.py:699`

```python
except aiohttp.ServerTimeoutError:
    # retry + backoff + circuit-breaker logic
```

**Root cause**

The shared session is built with a **total** timeout
(`http_client.py:124`: `ClientTimeout(total=Config.REQUEST_TIMEOUT, connect=5, sock_read=...)`).
The `total` timeout is the one most likely to fire on a slow site — but aiohttp does
**not** raise `ServerTimeoutError` for it.

Verified against the official aiohttp docs (via Context7):

> *ServerTimeoutError — Server operation timeout: read timeout, etc.*
> ***To catch all timeouts, including the `total` timeout, use `asyncio.TimeoutError`.***

`ServerTimeoutError` is a *subclass* of `asyncio.TimeoutError`, not the reverse. A `total`
timeout raises a plain `asyncio.TimeoutError`, which is **not** caught at line 699 and
falls through to the generic `except Exception` at `gateway_checker.py:747`.

**Impact**

- ❌ No retry — the timeout retry/backoff branch is skipped entirely.
- ❌ No `_circuit_breaker.record_failure()` — a slow/dead domain never trips the breaker,
  so every future scan keeps paying the full timeout instead of being short-circuited.
- ❌ The user sees `"Error: "` — **literally empty** — because
  `str(asyncio.TimeoutError())` is `""` (the generic handler builds `f"Error: {str(e)}"`).

This defeats the retry + circuit-breaker design for the single most common failure mode.

**Fix**

`asyncio` is already imported. Catching `asyncio.TimeoutError` also catches
`ServerTimeoutError` (subclass) and remains correctly ordered before the
`ClientConnectionError` handler that follows.

```diff
- except aiohttp.ServerTimeoutError:
+ except asyncio.TimeoutError:   # covers total, sock_read, sock_connect, and ServerTimeoutError
      # Retry timeouts - could be temporary network congestion
      if retry_count < MAX_RETRIES:
          delay = RETRY_DELAY * (RETRY_BACKOFF**retry_count)
          logger.warning(f"Timeout for {url}, retrying in {delay}s...")
          await asyncio.sleep(delay)
          return await check_url(url, session, retry_count + 1, use_cache)

      await _circuit_breaker.record_failure(url)
      logger.error(f"Timeout for {url} after {MAX_RETRIES} retries")
      return ([], 408, False, False, "Request Timeout", "N/A", "N/A",
              "None detected", "None detected")
```

**Verification**

- Unit: point `check_url` at a deliberately slow endpoint (e.g. `httpbin.org/delay/30`)
  with `REQUEST_TIMEOUT=2`; assert it returns status `408 "Request Timeout"` (not `500 "Error: "`)
  and that `get_circuit_breaker_stats()` shows a recorded failure after `MAX_RETRIES`.
- Regression: confirm a normal 200 page still succeeds and resets the breaker.

---

## Bug 2 — Aho-Corasick matcher is dead code 🟠

**Location:** `pattern_matcher.py` (entire 402-line module) + `requirements.txt`

**Root cause**

`pattern_matcher.py` advertises itself as *"the primary entry point for pattern matching"*
and *"10-20x faster than linear regex scanning"*, and `requirements.txt` pins
`pyahocorasick>=2.0.0` specifically for it. But **nothing imports** `find_gateways_fast`
or `get_pattern_matcher` outside the module itself (verified by repo-wide grep).

The detection actually used is `detection.find_payment_gateways_optimized`
(`detection.py:668`, called at `detection.py:1142`), which does **linear regex scanning**
over every pattern tier.

**Impact**

- The advertised speedup is never realized.
- `pyahocorasick` is a required dependency that does nothing.
- Two parallel pattern catalogs now drift independently (the `pattern_matcher.py` set is
  much smaller and already stale vs. `detection.py`'s `SDK_PATTERNS` / `WORD_BOUNDARY_GATEWAYS`).

**Fix — pick one**

- **Option A (recommended once Power-ups #1/#2 land):** wire it in. Feed the *combined*
  text (homepage + checkout pages + fetched JS bundles) through `find_gateways_fast`
  as a fast pre-filter, then run the high-confidence regex tiers only for gateways the
  automaton flagged. This is where O(n+m) actually pays off, because you'll be scanning
  far more text.
- **Option B (do now):** delete `pattern_matcher.py` and drop `pyahocorasick` from
  `requirements.txt`. Removes a misleading "primary entry point" and an unused dependency.

Do **not** leave it half-wired as-is.

---

## Bug 3 — Duplicate URLs in a batch lose results 🟡

**Location:** `bot_aiogram.py:2655-2670`

```python
url_to_idx = {url: i for i, url in enumerate(urls)}              # collapses duplicates
pending_tasks = {asyncio.create_task(task): url for task, url in zip(tasks, urls)}
...
idx = url_to_idx[url]            # same idx for both duplicates
responses[idx] = await task      # second result overwrites the first
```

**Root cause**

Both the index map and the task map are keyed by URL string. If the same URL appears
twice in a batch, the two tasks resolve to a single index; one result overwrites the
other and the orphaned `responses` slot stays `None`.

**Impact**

A `None` slot later hits the unpack at `bot_aiogram.py:2706`
(`detected_gateways, ... = response`), raising `TypeError` that the per-item
`try/except` (`:2712`) renders as a spurious "🔴 ERROR" card. Net effect: duplicate
input silently loses a real result.

**Fix**

Key the bookkeeping by task identity / position, not by URL:

```diff
- url_to_idx = {url: i for i, url in enumerate(urls)}
- pending_tasks = {asyncio.create_task(task): url for task, url in zip(tasks, urls)}
+ created = [asyncio.create_task(task) for task in tasks]
+ task_to_idx = {t: i for i, t in enumerate(created)}
+ pending_tasks = dict(task_to_idx)   # task -> idx
  responses = [None] * total

  while pending_tasks:
      done, pending = await asyncio.wait(pending_tasks.keys(),
                                         return_when=asyncio.FIRST_COMPLETED)
      for task in done:
-         url = pending_tasks[task]
-         idx = url_to_idx[url]
+         idx = pending_tasks[task]
+         url = urls[idx]
          responses[idx] = await task   # see Bug 4 for the guard
          del pending_tasks[task]
```

---

## Bug 4 — Progress branch has no exception guard 🟡

**Location:** `bot_aiogram.py:2669`

```python
responses[idx] = await task     # re-raises if the task raised
```

**Root cause**

The multi-URL progress path awaits each task with no protection, unlike the single-URL
fallback at `bot_aiogram.py:2684` which uses `asyncio.gather(*tasks, return_exceptions=True)`.

**Impact**

Currently safe *only* because `check_url` swallows every exception and always returns a
tuple. But it's fragile: any future code path that raises (or the `KeyError`/`TypeError`
from the Bug 3 duplicate case) aborts the **entire** batch mid-flight, losing all
pending results.

**Fix**

Capture exceptions per task so the batch matches the `return_exceptions=True` semantics
the formatter at `:2689` already expects:

```diff
- responses[idx] = await task
+ try:
+     responses[idx] = await task
+ except Exception as e:        # noqa: BLE001 — mirror gather(return_exceptions=True)
+     responses[idx] = e
```

---

## Bug 5 — Dead legacy detectors in utils.py ⚪

**Location:** `utils.py` — `find_payment_gateways` (`:78`), `check_captcha` (`:98`),
`check_cloudflare` (`:112`), `check_3d_secure` (`:130`), `check_otp_required` (`:144`),
`check_payment_info` (`:158`), `check_inbuilt_payment_system` (`:183`).

**Root cause**

All seven are superseded by `detection.py` and have **zero callers** (verified by grep;
the apparent `detection.py` matches are its own same-named functions, not imports from
`utils`). `find_payment_gateways` still does naive case-insensitive substring matching
(`utils.py:91`) — exactly the false-positive problem (`"stripe"` inside `"pinstripe"`)
that `detection.py`'s word-boundary tiers were built to eliminate.

**Impact**

No runtime impact. Maintenance/clarity cost: a reader can't tell which detector is live,
and the dead substring matcher is a tempting trap to "reuse."

**Fix**

Delete the seven functions and prune the now-unused imports at `utils.py:5-8`
(`PAYMENT_GATEWAYS`, `CAPTCHA_KEYWORDS`, `CLOUDFLARE_INDICATORS`, `SECURE_3D_KEYWORDS`,
`OTP_KEYWORDS`, `INBUILT_PAYMENT_KEYWORDS`). Keep `escape_markdown`, `normalize_url`,
`is_valid_url`, and `format_url_result`, which *are* used. If you want to keep
`PAYMENT_GATEWAYS` for reference, leave it in `config.py` — it just shouldn't drive
detection.

---

## Power-ups — making detection more powerful

The dominant limiter is **what gets fetched**, not the pattern set. Ranked by impact.

### P1 — Scan checkout / cart / pricing pages, not just the homepage  ⭐ highest leverage

`check_url` fetches only the submitted URL, which is almost always the homepage. Payment
SDKs (Stripe, Adyen, Braintree, Razorpay…) overwhelmingly load on `/checkout`, `/cart`,
`/payment`, `/donate`, `/pricing`, `/subscribe`, `/shop`. Probing a handful of likely
paths and merging detections is the single biggest hit-rate gain.

**Implementation sketch** (new helper, called by `check_url` after the homepage scan):

```python
CANDIDATE_PATHS = ("/checkout", "/cart", "/payment", "/pricing",
                   "/subscribe", "/donate", "/shop", "/store")

async def _probe_checkout_pages(base_url, session, headers, found):
    """Fetch a few likely-payment paths concurrently; merge new gateways."""
    from urllib.parse import urljoin
    targets = [urljoin(base_url, p) for p in CANDIDATE_PATHS]
    async def fetch(u):
        try:
            async with session.get(u, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT),
                                   allow_redirects=True) as r:
                if r.status != 200:
                    return None
                return await _stream_response_text(r)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            return None
    pages = await asyncio.gather(*(fetch(u) for u in targets))
    for html in filter(None, pages):
        more = analyze_url_response(html, {}, 200)
        found.update(more["gateways"])     # union of detections across pages
    return found
```

Design choices for you:
- **Discovery vs. guessing:** also parse the homepage for anchor/button links containing
  `cart|checkout|buy|subscribe|donate` and follow those (more accurate than blind paths).
- **Budget:** cap at ~3-4 extra fetches per domain and run them concurrently so latency
  stays bounded; reuse the existing per-host connection pool (`limit_per_host=30`).
- **Caching:** cache the *merged* per-domain result, not per-URL, to avoid re-probing.

### P2 — Fetch and scan external `<script src>` bundles

`html_parser.py` already *parses out* every script URL (`_extract_scripts`, `:354`) but
never downloads them. Gateways initialized inside bundled first-party JS (e.g. a minified
`app.[hash].js` that calls `Stripe(...)`) are invisible to a static HTML scan.

**Implementation sketch:**

```python
async def _scan_first_party_scripts(structure, base_url, session, headers, found):
    from urllib.parse import urljoin, urlparse
    base_host = urlparse(base_url).netloc
    # only same-origin scripts without an already-known gateway hint, cap to top N
    srcs = [s.src for s in structure.scripts
            if s.src and not s.gateway_hint
            and urlparse(urljoin(base_url, s.src)).netloc == base_host][:5]
    for src in srcs:
        try:
            async with session.get(urljoin(base_url, src), headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    js = await _stream_response_text(r, cap=512_000)
                    names, _ = find_payment_gateways_optimized(js)
                    found.update(names)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            continue
    return found
```

Guards: same-origin only (don't crawl CDNs/trackers), cap count and per-file size,
skip scripts already attributed to a gateway.

### P3 — Raise / condition the 512 KB body cap

`gateway_checker.py:48` `MAX_RESPONSE_BYTES = 512_000`. Checkout scripts often sit late in
large pages and get truncated. Raise the cap (e.g. 1 MB) for checkout/cart fetches
specifically, or make the cap a parameter so P1's checkout probes can use a larger window
than homepage scans.

### P4 — Fix the client-hint / User-Agent fingerprint mismatch

`gateway_checker.py:407` rotates the `User-Agent` randomly, but lines 427-429 send
**hardcoded** Chrome-120 client hints:

```python
"Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
"Sec-Ch-Ua-Mobile": "?0",
"Sec-Ch-Ua-Platform": '"Windows"',
```

A random Firefox/mobile UA paired with Chrome-120 client hints is an internally
inconsistent fingerprint that modern WAFs (Cloudflare, Akamai, Datadome) flag — it can
*reduce* your bypass rate. **Fix:** derive `Sec-Ch-Ua*` from the chosen UA, or omit those
headers entirely when the UA isn't Chromium-based. Keep them only for Chrome UAs.

### P5 — Optional JS rendering for client-rendered checkouts (Playwright)

Some checkouts are fully client-rendered; no static fetch (even of JS bundles) reveals the
gateway until scripts execute. A headless browser is the only reliable catch. Keep it
**opt-in / fallback only** (heavy: ~100-300 MB, slow): run it just for domains where the
static + checkout-probe + JS-scan passes all returned zero gateways. Gate behind a config
flag so the default path stays fast.

### P6 — Then wire in Aho-Corasick (closes Bug 2)

Once P1+P2 multiply the volume of text scanned (multiple pages + JS bundles), the
`pattern_matcher.py` automaton becomes genuinely worthwhile as a fast pre-filter. Use it to
narrow the candidate gateway set, then confirm with `detection.py`'s high-confidence regex
tiers. Before doing this, reconcile the two pattern catalogs so they don't drift.

---

## Prioritized roadmap

| # | Item | Type | Effort | Risk | Payoff |
|---|------|------|--------|------|--------|
| 1 | **Bug 1** — catch `asyncio.TimeoutError` | Fix | 1 line | Very low | High — retries + circuit breaker + no empty errors |
| 2 | **P1** — checkout/cart page probing | Feature | M | Low-Med | Highest detection-rate gain |
| 3 | **P2** — scan first-party JS bundles | Feature | M | Low | High |
| 4 | **P4** — UA / client-hint consistency | Fix | S | Low | Better WAF bypass |
| 5 | **Bug 3 + Bug 4** — batch dedup + guard | Fix | S | Low | Correctness/robustness |
| 6 | **P3** — conditional body cap | Tweak | S | Low | Medium |
| 7 | **Bug 2 / P6** — decide Aho-Corasick (wire in or delete) | Cleanup/Perf | S-M | Low | Perf + clarity |
| 8 | **Bug 5** — delete dead `utils.py` detectors | Cleanup | S | Very low | Maintainability |
| 9 | **P5** — Playwright fallback (opt-in) | Feature | L | Med | Catches the hardest sites |

**Suggested first PR:** Bug 1 + Bug 3 + Bug 4 + Bug 5 (small, safe, high-value correctness
batch). **Second PR:** P1 + P2 + P4 (the detection-power upgrade). **Later:** P3/P6/P5.
