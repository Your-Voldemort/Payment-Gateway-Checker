"""Payment gateway checking functionality with optimized detection, retry logic, and result caching."""

import aiohttp
import asyncio
import time
from typing import Tuple, List, Optional
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

    # Create session if not provided
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

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
            text = await response.text()

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
        # Close session if we created it
        if close_session:
            await session.close()
