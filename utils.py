"""Utility functions for URL validation and analysis."""
import validators
from typing import List


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


def format_url_result(
    url: str,
    detected_gateways: List[str],
    status_code: int,
    captcha: bool,
    cloudflare: bool,
    payment_security_type: str,
    cvv_cvc_status: str,
    inbuilt_status: str,
    ecommerce_platform: str = "None detected",
    cart_abandonment: str = "None detected"
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
        ecommerce_platform: Detected e-commerce platform name
        cart_abandonment: Detected cart abandonment tools summary

    Returns:
        str: Formatted result string (plain text, no Markdown)
    """
    # URL display (truncate if too long for readability)
    display_url = url if len(url) <= 50 else url[:47] + "..."

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
    
    # E-commerce platform formatting
    if ecommerce_platform and ecommerce_platform != "None detected":
        platform_display = f"🛒 {ecommerce_platform}"
    else:
        platform_display = "⚪ None detected"
    
    # Cart abandonment tools formatting
    if cart_abandonment and cart_abandonment != "None detected":
        # Truncate if too long
        cart_display = cart_abandonment if len(cart_abandonment) <= 40 else cart_abandonment[:37] + "..."
        cart_display = f"🛡️ {cart_display}"
    else:
        cart_display = "⚪ None detected"

    return (
        f"╭─ SCAN RESULT ─────────────╮\n"
        f"│  🌐 {display_url}\n"
        f"│  {status_display}\n"
        f"╰───────────────────────────╯\n"
        f"\n"
        f"┌─ 💳 GATEWAYS ──────────────\n"
        f"│\n"
        f"│  {gateways_str}\n"
        f"│\n"
        f"└────────────────────────────\n"
        f"\n"
        f"┌─ 🛒 PLATFORM ──────────────\n"
        f"│\n"
        f"│  {platform_display}\n"
        f"│\n"
        f"└────────────────────────────\n"
        f"\n"
        f"┌─ 🛡️ CART PROTECTION ───────\n"
        f"│\n"
        f"│  {cart_display}\n"
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
