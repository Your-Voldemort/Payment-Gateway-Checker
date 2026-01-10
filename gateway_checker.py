"""Payment gateway checking functionality with optimized detection and retry logic."""
import aiohttp
import asyncio
from typing import Tuple, List
from config import Config
from utils import is_valid_url
from detection import analyze_url_response
from user_agents import get_random_user_agent
from logger import setup_logger

logger = setup_logger()

# Retry configuration for transient failures
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
RETRY_BACKOFF = 2  # exponential backoff multiplier


async def check_url(
    url: str,
    session: aiohttp.ClientSession = None,
    retry_count: int = 0
) -> Tuple[List[str], int, bool, bool, str, str, str]:
    """
    Check the provided URL for payment gateways, security features, and IP info.
    Includes automatic retry logic for transient failures (5xx errors, timeouts, connection errors).

    Args:
        url: The URL to check
        session: Optional aiohttp ClientSession for connection reuse
        retry_count: Current retry attempt (internal use, starts at 0)

    Returns:
        Tuple containing:
            - List of detected payment gateways
            - HTTP status code
            - Captcha detected (bool)
            - Cloudflare detected (bool)
            - Payment security type description
            - CVV/CVC requirement status
            - Inbuilt payment system status
    """
    if not is_valid_url(url):
        logger.warning(f"Invalid URL provided: {url}")
        return [], 400, False, False, "Invalid URL", "N/A", "N/A"

    # Use rotating user agent to minimize rate limiting
    user_agent = get_random_user_agent()
    
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    # Create session if not provided
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        attempt_info = f" (attempt {retry_count + 1}/{MAX_RETRIES + 1})" if retry_count > 0 else ""
        logger.info(f"Checking URL: {url}{attempt_info}")

        timeout = aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT)
        async with session.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            ssl=True
        ) as response:
            response.raise_for_status()
            text = await response.text()

            # Use the new optimized detection module
            # This provides word-boundary matching, SDK detection, and header analysis
            analysis = analyze_url_response(
                html=text,
                headers=dict(response.headers),
                status_code=response.status
            )

            logger.info(f"Successfully checked {url} - Status: {response.status}, "
                       f"Gateways: {len(analysis['gateways'])} "
                       f"(High confidence: {len(analysis['high_confidence_gateways'])})")

            return (
                analysis['gateways'],
                response.status,
                analysis['captcha'],
                analysis['cloudflare'],
                analysis['security_type'],
                analysis['cvv_status'],
                analysis['inbuilt_status']
            )

    except aiohttp.ClientResponseError as http_err:
        status_code = http_err.status

        # Don't retry client errors (4xx) - these are permanent
        if 400 <= status_code < 500:
            logger.error(f"HTTP client error for {url}: {status_code}")
            if status_code == 403:
                return [], 403, False, False, "403 Forbidden: Access Denied", "N/A", "N/A"
            else:
                return [], status_code, False, False, f"HTTP Error: {status_code}", "N/A", "N/A"

        # Retry server errors (5xx) - these are often transient
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAY * (RETRY_BACKOFF ** retry_count)
            logger.warning(f"Server error {status_code} for {url}, retrying in {delay}s...")
            await asyncio.sleep(delay)
            return await check_url(url, session, retry_count + 1)

        logger.error(f"HTTP error for {url} after {MAX_RETRIES} retries: {status_code}")
        return [], status_code, False, False, f"HTTP Error: {status_code}", "N/A", "N/A"

    except aiohttp.ServerTimeoutError:
        # Retry timeouts - could be temporary network congestion
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAY * (RETRY_BACKOFF ** retry_count)
            logger.warning(f"Timeout for {url}, retrying in {delay}s...")
            await asyncio.sleep(delay)
            return await check_url(url, session, retry_count + 1)

        logger.error(f"Timeout for {url} after {MAX_RETRIES} retries")
        return [], 408, False, False, "Request Timeout", "N/A", "N/A"

    except aiohttp.ClientConnectionError as conn_err:
        # Retry connection errors - network issues are often temporary
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAY * (RETRY_BACKOFF ** retry_count)
            logger.warning(f"Connection error for {url}, retrying in {delay}s...")
            await asyncio.sleep(delay)
            return await check_url(url, session, retry_count + 1)

        logger.error(f"Connection error for {url} after {MAX_RETRIES} retries: {str(conn_err)}")
        return [], 503, False, False, "Connection Error", "N/A", "N/A"

    except Exception as e:
        logger.error(f"Unexpected error checking {url}: {str(e)}")
        return [], 500, False, False, f"Error: {str(e)}", "N/A", "N/A"
    
    finally:
        # Close session if we created it
        if close_session:
            await session.close()
