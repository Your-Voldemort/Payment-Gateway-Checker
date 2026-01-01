"""Utility functions for URL validation and analysis."""
import re
import validators
from typing import Tuple, List
from config import (
    PAYMENT_GATEWAYS, CAPTCHA_KEYWORDS, CLOUDFLARE_INDICATORS,
    SECURE_3D_KEYWORDS, OTP_KEYWORDS, INBUILT_PAYMENT_KEYWORDS
)


def normalize_url(url: str) -> str:
    """
    Normalize URL by adding https:// protocol if missing.
    
    Handles various URL formats:
    - xyz.com -> https://xyz.com
    - www.xyz.com -> https://www.xyz.com
    - https://xyz.com -> https://xyz.com (no change)
    - http://xyz.com -> http://xyz.com (no change)
    
    Args:
        url: URL string to normalize
        
    Returns:
        str: Normalized URL with protocol
    """
    url = url.strip()
    
    # If URL already has a protocol, return as is
    if url.startswith(('http://', 'https://')):
        return url
    
    # Add https:// protocol
    return f'https://{url}'


def is_valid_url(url: str) -> bool:
    """
    Validate URL using the validators library.
    
    Args:
        url: URL string to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    return validators.url(url) is True


def find_payment_gateways(response_text: str) -> List[str]:
    """
    Detect payment gateways from the response text.
    
    Args:
        response_text: HTML response text
        
    Returns:
        List of detected payment gateway names
    """
    detected_gateways = []
    response_lower = response_text.lower()
    
    for gateway in PAYMENT_GATEWAYS:
        if gateway in response_lower:
            detected_gateways.append(gateway.capitalize())
    
    return list(set(detected_gateways))  # Remove duplicates


def check_captcha(response_text: str) -> bool:
    """
    Check for Captcha presence in the response text.
    
    Args:
        response_text: HTML response text
        
    Returns:
        bool: True if captcha is detected
    """
    response_lower = response_text.lower()
    return any(keyword in response_lower for keyword in CAPTCHA_KEYWORDS)


def check_cloudflare(headers: dict, response_text: str) -> bool:
    """
    Check for Cloudflare protection based on headers and response text.
    
    Args:
        headers: Response headers dictionary
        response_text: HTML response text
        
    Returns:
        bool: True if Cloudflare is detected
    """
    if "server" in headers and headers["server"].lower() == "cloudflare":
        return True
    
    response_lower = response_text.lower()
    return any(indicator in response_lower for indicator in CLOUDFLARE_INDICATORS)


def check_3d_secure(response_text: str) -> bool:
    """
    Check for 3D Secure indicators in the response text.
    
    Args:
        response_text: HTML response text
        
    Returns:
        bool: True if 3D Secure is detected
    """
    response_lower = response_text.lower()
    return any(keyword in response_lower for keyword in SECURE_3D_KEYWORDS)


def check_otp_required(response_text: str) -> bool:
    """
    Check for OTP requirement indicators in the response text.
    
    Args:
        response_text: HTML response text
        
    Returns:
        bool: True if OTP is required
    """
    response_lower = response_text.lower()
    return any(keyword in response_lower for keyword in OTP_KEYWORDS)


def check_payment_info(response_text: str) -> str:
    """
    Analyze payment page text for specific CVV and CVC requirements.
    
    Args:
        response_text: HTML response text
        
    Returns:
        str: CVV/CVC requirement status
    """
    response_lower = response_text.lower()
    
    cvv_required = "cvv" in response_lower
    cvc_required = "cvc" in response_lower
    
    if cvv_required and cvc_required:
        return "Both CVV and CVC Required"
    elif cvv_required:
        return "CVV Required"
    elif cvc_required:
        return "CVC Required"
    else:
        return "No CVV or CVC Requirement Detected"


def check_inbuilt_payment_system(response_text: str, inbuilt_keywords: List[str] = None) -> bool:
    """
    Check if the site has an inbuilt payment system based on specific keywords.
    
    Args:
        response_text: The text response from the site to analyze
        inbuilt_keywords: Optional list of keywords to check for
        
    Returns:
        bool: True if any keyword is found, False otherwise
    """
    if inbuilt_keywords is None:
        inbuilt_keywords = INBUILT_PAYMENT_KEYWORDS
    
    response_lower = response_text.lower()
    
    # Create a regex pattern for exact whole word matching
    pattern = r'\b(?:' + '|'.join(map(re.escape, inbuilt_keywords)) + r')\b'
    
    return bool(re.search(pattern, response_lower))


def format_url_result(
    url: str,
    detected_gateways: List[str],
    status_code: int,
    captcha: bool,
    cloudflare: bool,
    payment_security_type: str,
    cvv_cvc_status: str,
    inbuilt_status: str
) -> str:
    """
    Format the URL check result into a readable message.
    
    Args:
        url: The checked URL
        detected_gateways: List of detected payment gateways
        status_code: HTTP status code
        captcha: Whether captcha was detected
        cloudflare: Whether Cloudflare was detected
        payment_security_type: Type of payment security
        cvv_cvc_status: CVV/CVC requirement status
        inbuilt_status: Inbuilt payment system status
        
    Returns:
        str: Formatted result string
    """
    gateways_str = ', '.join(detected_gateways) if detected_gateways else "None"
    
    return (
        f"🔹 URL: {url}\n"
        f"🔹 Payment Gateways: {gateways_str}\n"
        f"🔹 Captcha Detected: {captcha}\n"
        f"🔹 Cloudflare Detected: {cloudflare}\n"
        f"🔹 Payment Security Type: {payment_security_type}\n"
        f"🔹 CVV/CVC Requirement: {cvv_cvc_status}\n"
        f"🔹 Inbuilt Payment System: {inbuilt_status}\n"
        f"🔹 Status Code: {status_code}\n"
        "━━━━━━━━━━━━━━\n"
    )
