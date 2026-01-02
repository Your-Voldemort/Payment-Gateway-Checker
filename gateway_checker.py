"""Payment gateway checking functionality with optimized detection."""
import aiohttp
from typing import Tuple, List
from config import Config
from utils import is_valid_url
from detection import analyze_url_response
from user_agents import get_random_user_agent
from logger import setup_logger

logger = setup_logger()


async def check_url(url: str, session: aiohttp.ClientSession = None) -> Tuple[List[str], int, bool, bool, str, str, str]:
    """
    Check the provided URL for payment gateways, security features, and IP info.
    
    Args:
        url: The URL to check
        session: Optional aiohttp ClientSession for connection reuse
        
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
        logger.info(f"Checking URL: {url}")

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
        logger.error(f"HTTP error checking {url}: {status_code} - {str(http_err)}")
        
        if status_code == 403:
            return [], 403, False, False, "403 Forbidden: Access Denied", "N/A", "N/A"
        else:
            return [], status_code, False, False, f"HTTP Error: {status_code}", "N/A", "N/A"
            
    except aiohttp.ServerTimeoutError:
        logger.error(f"Timeout while checking {url}")
        return [], 408, False, False, "Request Timeout", "N/A", "N/A"
        
    except aiohttp.ClientConnectionError as conn_err:
        logger.error(f"Connection error checking {url}: {str(conn_err)}")
        return [], 503, False, False, "Connection Error", "N/A", "N/A"
        
    except Exception as e:
        logger.error(f"Request exception checking {url}: {str(e)}")
        return [], 500, False, False, f"Error: {str(e)}", "N/A", "N/A"
    
    finally:
        # Close session if we created it
        if close_session:
            await session.close()
