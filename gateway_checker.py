"""Payment gateway checking functionality with optimized detection, retry logic, and result caching."""

import aiohttp
import asyncio
import time
from typing import Tuple, List
from urllib.parse import urlparse
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

# Retry configuration for transient failures
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
RETRY_BACKOFF = 2  # exponential backoff multiplier


async def check_url(
    url: str,
    session: aiohttp.ClientSession = None,
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

    # Extract hostname from URL for Host/Origin headers (Phase 2 bypass improvement)
    from urllib.parse import urlparse

    parsed_url = urlparse(url)
    hostname = parsed_url.netloc or parsed_url.hostname or ""

    # Enhanced headers to bypass 403/400 errors and appear as real browser
    # Phase 1: User-Agent rotation, enhanced Accept headers, security headers
    # Phase 2: Host/Origin headers, pragma/cache headers for realistic requests
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,en-GB;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Charset": "utf-8;q=0.7,*;q=0.7",
        "Host": hostname,  # 🔑 Critical: Match target domain
        "Origin": f"https://{hostname}",  # 🔑 Same-origin request appearance
        "Referer": f"https://{hostname}/",  # Self-referral instead of Google (less suspicious for 400)
        "DNT": "1",
        "Connection": "keep-alive",
        "Keep-Alive": "timeout=5, max=100",
        "Upgrade-Insecure-Requests": "1",
        "Pragma": "no-cache",  # Realistic browser caching header
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "If-None-Match": "",  # Simulate conditional request (seen in real browsers)
        "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",  # Realistic cache timestamp
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
            url, headers=headers, timeout=timeout, allow_redirects=True, ssl=True
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
                # Phase 3: Try /index.html variant for bare domains
                parsed = urlparse(url)
                path = parsed.path or ""

                if (
                    not path
                    or path == "/"
                    or not path.endswith((".html", ".php", ".aspx", "/"))
                ):
                    # Try adding /index.html
                    variant_url = url.rstrip("/") + "/index.html"
                    if "?" not in variant_url:
                        variant_url += "?_t=" + str(int(time.time() * 1000))

                    logger.warning(
                        f"Bad Request (400) for {url} - trying /index.html variant..."
                    )
                    await asyncio.sleep(0.5)
                    return await check_url(variant_url, session, retry_count, use_cache)

                logger.warning(
                    f"Bad Request (400) for {url} - server rejected request format. "
                    f"Possible causes: Server requires authentication, API key, or blocks bot traffic. "
                    f"Attempted with enhanced headers, Host/Origin fields, and trailing slash handling."
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
