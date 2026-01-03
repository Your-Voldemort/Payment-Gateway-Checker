"""Utility functions for URL validation and analysis."""
import re
import validators
from typing import Tuple, List, Optional
from config import (
    PAYMENT_GATEWAYS, CAPTCHA_KEYWORDS, CLOUDFLARE_INDICATORS,
    SECURE_3D_KEYWORDS, OTP_KEYWORDS, INBUILT_PAYMENT_KEYWORDS
)


def escape_markdown(text: str) -> str:
    """
    Escape special Markdown characters to prevent Telegram parse errors.
    
    Telegram's Markdown parser is strict and will fail if special characters
    like _, *, `, [, ] are not properly escaped or balanced.
    
    Args:
        text: The text to escape
        
    Returns:
        str: Text with Markdown special characters escaped
    """
    if not text:
        return text
    
    # Characters that need escaping in Telegram Markdown
    # Note: We escape _ and * which are most common issues
    # We also escape ` [ ] ( ) which can cause parsing issues
    escape_chars = ['_', '*', '`', '[', ']', '(', ')']
    
    result = text
    for char in escape_chars:
        result = result.replace(char, '\\' + char)
    
    return result


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


def check_inbuilt_payment_system(response_text: str, inbuilt_keywords: Optional[List[str]] = None) -> bool:
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

    Uses a modern card-based design with rounded corners, chevron bullets,
    and proper vertical spacing for improved readability.

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
        str: Formatted result string (plain text, no Markdown)
    """
    # URL display (truncate if too long for readability)
    display_url = url if len(url) <= 24 else url[:21] + "..."

    # Status indicator with color coding
    if status_code == 200:
        status_display = f"🟢 {status_code} OK"
    elif status_code in [301, 302, 303, 307, 308]:
        status_display = f"🟡 {status_code} Redirect"
    elif status_code == 403:
        status_display = f"🟠 {status_code} Forbidden"
    elif status_code == 404:
        status_display = f"🔴 {status_code} Not Found"
    elif status_code >= 500:
        status_display = f"🔴 {status_code} Server Error"
    else:
        status_display = f"⚪ {status_code}"

    # Format gateways - show all detected gateways
    if detected_gateways:
        gateways_str = f"✅ {', '.join(detected_gateways)}"
    else:
        gateways_str = "❌ None detected"

    # Security type formatting - simplify display
    security_lower = payment_security_type.lower()
    if "3d" in security_lower or "secure" in security_lower:
        auth_display = "3D Secure"
    elif "otp" in security_lower:
        auth_display = "OTP Required"
    elif "none" in security_lower or "no " in security_lower:
        auth_display = "None"
    else:
        auth_display = payment_security_type

    # CVV/CVC formatting - simplify display
    cvv_lower = cvv_cvc_status.lower()
    if "both" in cvv_lower:
        cvv_display = "CVV + CVC"
    elif "cvv" in cvv_lower and "required" in cvv_lower:
        cvv_display = "Required"
    elif "cvc" in cvv_lower and "required" in cvv_lower:
        cvv_display = "Required"
    elif "no " in cvv_lower or "none" in cvv_lower:
        cvv_display = "Not detected"
    else:
        cvv_display = cvv_cvc_status

    # Inbuilt status formatting
    inbuilt_lower = inbuilt_status.lower()
    if "detected" in inbuilt_lower or "yes" in inbuilt_lower:
        inbuilt_display = "Detected"
    else:
        inbuilt_display = "Not detected"

    # Cloudflare formatting
    if cloudflare:
        cf_display = "🛡️ Protected"
    else:
        cf_display = "⚪ None"

    # Captcha formatting
    if captcha:
        captcha_display = "🤖 Detected"
    else:
        captcha_display = "⚪ None"

    return (
        f"╭─ SCAN RESULT ─────────────╮\n"
        f"│  🌐 {display_url}\n"
        f"│  {status_display}\n"
        f"╰───────────────────────────╯\n"
        f"\n"
        f"┌─ 💳 GATEWAYS ─────────────\n"
        f"│\n"
        f"│  {gateways_str}\n"
        f"│\n"
        f"└────────────────────────────\n"
        f"\n"
        f"┌─ 🔐 SECURITY ─────────────\n"
        f"│\n"
        f"│  Auth     ›  {auth_display}\n"
        f"│  CVV/CVC  ›  {cvv_display}\n"
        f"│  Inbuilt  ›  {inbuilt_display}\n"
        f"│\n"
        f"└────────────────────────────\n"
        f"\n"
        f"┌─ 🛡️ PROTECTION ───────────\n"
        f"│\n"
        f"│  Cloudflare  ›  {cf_display}\n"
        f"│  Captcha     ›  {captcha_display}\n"
        f"│\n"
        f"└────────────────────────────\n\n"
    )
