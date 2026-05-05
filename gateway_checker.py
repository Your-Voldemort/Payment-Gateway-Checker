"""Payment gateway checking functionality with optimized detection, retry logic, and result caching."""

import aiohttp
import asyncio
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


def _fetch_with_curl_cffi(url: str, timeout: int = 15) -> Tuple[str, int, dict]:
    """
    Fetch URL using curl_cffi with Chrome browser impersonation.

    This bypasses TLS/JA3 fingerprinting used by CDNs like Fastly, Cloudflare, Akamai.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (html_content, status_code, headers_dict)

    Raises:
        Exception on network/request errors
    """
    if not CURL_CFFI_AVAILABLE:
        raise RuntimeError("curl_cffi not available")

    response = curl_requests.get(
        url,
        impersonate="chrome",  # Impersonate Chrome browser TLS fingerprint
        timeout=timeout,
        allow_redirects=True,
    )
    return response.text, response.status_code, dict(response.headers)


async def _async_fetch_with_curl_cffi(
    url: str, timeout: int = 15
) -> Tuple[str, int, dict]:
    """
    Async wrapper for curl_cffi fetch (runs in thread pool).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _curl_executor, _fetch_with_curl_cffi, url, timeout
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
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }

    # Use the shared persistent connection pool if no session is passed.
    # Previously this created a fresh aiohttp.ClientSession() (and a new TCP
    # pool) on every call, leaking connections.  Now we always default to the
    # module-level singleton from http_client.py.
    close_session = False
    if session is None:
        session = await get_http_session()  # Shared pool — never close this
        close_session = False

    try:
        attempt_info = (
            f" (attempt {retry_count + 1}/{MAX_RETRIES + 1})" if retry_count > 0 else ""
        )
        logger.info(f"Checking URL: {url}{attempt_info}")

        # Add small delay to appear more human-like and reduce bot detection
        await asyncio.sleep(0.3)

        timeout = aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT)
        async with session.get(
            url, headers=headers, timeout=timeout, allow_redirects=True
        ) as response:
            response.raise_for_status()
            # Stream up to MAX_RESPONSE_BYTES to avoid OOM on large pages.
            # Detection targets (<head>, early <body>) are always in the first 500 KB.
            text = await _stream_response_text(response)

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

                elif retry_count == 1 and CURL_CFFI_AVAILABLE:
                    # Second fallback: use curl_cffi with browser TLS impersonation
                    # This bypasses CDN/WAF TLS fingerprinting (JA3/JA4)
                    logger.warning(
                        f"Bad Request (400) for {url} - retrying with curl_cffi (browser TLS)..."
                    )
                    try:
                        (
                            text,
                            curl_status,
                            curl_headers,
                        ) = await _async_fetch_with_curl_cffi(
                            url, timeout=Config.REQUEST_TIMEOUT
                        )

                        # Apply the same size cap to curl_cffi responses.
                        # curl_cffi returns the full body as a string; truncate
                        # to MAX_RESPONSE_BYTES worth of characters.
                        if len(text.encode("utf-8", errors="replace")) > MAX_RESPONSE_BYTES:
                            text = text.encode("utf-8", errors="replace")[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")
                            logger.warning(
                                f"curl_cffi response body capped at {MAX_RESPONSE_BYTES // 1024} KB for {url[:60]}"
                            )

                        if curl_status == 200:
                            logger.info(
                                f"curl_cffi succeeded for {url} - bypassed TLS fingerprinting"
                            )

                            # Use the detection module to analyze the response
                            analysis = analyze_url_response(
                                html=text, headers=curl_headers, status_code=curl_status
                            )
                            platform_detection = detect_ecommerce_platform(
                                html=text, headers=curl_headers
                            )
                            platform_name = (
                                platform_detection["platform"]
                                if platform_detection["platform"]
                                else "None detected"
                            )
                            cart_abandonment = detect_cart_abandonment_tools(
                                html=text, headers=curl_headers
                            )
                            cart_summary = cart_abandonment["summary"]

                            # Cache successful result
                            if use_cache:
                                cache_data = {
                                    "gateways": analysis["gateways"],
                                    "status_code": curl_status,
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
                                curl_status,
                                analysis["captcha"],
                                analysis["cloudflare"],
                                analysis["security_type"],
                                analysis["cvv_status"],
                                analysis["inbuilt_status"],
                                platform_name,
                                cart_summary,
                            )
                        else:
                            logger.warning(
                                f"curl_cffi got status {curl_status} for {url}"
                            )
                    except Exception as curl_err:
                        logger.error(f"curl_cffi failed for {url}: {curl_err}")

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

    except aiohttp.ServerTimeoutError:
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
