"""Payment gateway checking functionality."""
import requests
from typing import Tuple, List
from config import Config
from utils import (
    is_valid_url, find_payment_gateways, check_captcha, check_cloudflare,
    check_3d_secure, check_otp_required, check_payment_info,
    check_inbuilt_payment_system
)
from user_agents import get_random_user_agent
from logger import setup_logger

logger = setup_logger()


def check_url(url: str) -> Tuple[List[str], int, bool, bool, str, str, str]:
    """
    Check the provided URL for payment gateways, security features, and IP info.
    
    Args:
        url: The URL to check
        
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

    try:
        logger.info(f"Checking URL: {url}")
        response = requests.get(
            url,
            headers=headers,
            timeout=Config.REQUEST_TIMEOUT,
            allow_redirects=True,
            verify=True
        )
        response.raise_for_status()

        # Perform all checks
        detected_gateways = find_payment_gateways(response.text)
        captcha_detected = check_captcha(response.text)
        cloudflare_detected = check_cloudflare(response.headers, response.text)
        is_3d_secure = check_3d_secure(response.text)
        is_otp_required = check_otp_required(response.text)
        cvv_cvc_status = check_payment_info(response.text)
        inbuilt_payment = check_inbuilt_payment_system(response.text)

        # Determine payment security type
        payment_security_type = (
            "Both 3D Secure and OTP Required" if is_3d_secure and is_otp_required else
            "3D Secure" if is_3d_secure else
            "OTP Required" if is_otp_required else
            "2D (No extra security)"
        )
        
        if captcha_detected:
            payment_security_type += " | Captcha Detected"
        if cloudflare_detected:
            payment_security_type += " | Protected by Cloudflare"

        inbuilt_status = "Yes" if inbuilt_payment else "No"

        logger.info(f"Successfully checked {url} - Status: {response.status_code}, Gateways: {len(detected_gateways)}")
        return detected_gateways, response.status_code, captcha_detected, cloudflare_detected, payment_security_type, cvv_cvc_status, inbuilt_status

    except requests.exceptions.HTTPError as http_err:
        status_code = http_err.response.status_code if http_err.response else 500
        logger.error(f"HTTP error checking {url}: {status_code} - {str(http_err)}")
        
        if status_code == 403:
            return [], 403, False, False, "403 Forbidden: Access Denied", "N/A", "N/A"
        else:
            return [], status_code, False, False, f"HTTP Error: {status_code}", "N/A", "N/A"
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout while checking {url}")
        return [], 408, False, False, "Request Timeout", "N/A", "N/A"
        
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Connection error checking {url}: {str(conn_err)}")
        return [], 503, False, False, "Connection Error", "N/A", "N/A"
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception checking {url}: {str(e)}")
        return [], 500, False, False, f"Error: {str(e)}", "N/A", "N/A"
