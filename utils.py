"""Utility functions for URL validation, formatting, and analysis."""
import validators
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from detection import GatewayMatch


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


# =============================================================================
# P1-1: GATEWAY CATEGORIES — Regional/type grouping for detected gateways
# =============================================================================

GATEWAY_CATEGORIES: Dict[str, List[str]] = {
    "🌍 Global Major": [
        "Stripe", "PayPal", "Braintree", "Adyen", "Checkout.com",
        "Square", "Authorize.Net", "2Checkout", "Worldpay", "CyberSource",
    ],
    "🇪🇺 Europe": [
        "Mollie", "SagePay", "Trustly", "Giropay",
        "Przelewy24", "Bancontact", "Sofort", "iDEAL", "Fondy", "Datatrans",
    ],
    "🌏 APAC": [
        "Razorpay", "Paytm", "Alipay", "WeChat Pay", "UnionPay",
        "Cashfree", "PayU", "Juspay", "CCAvenue", "PhonePe",
        "Billdesk", "Bharat QR", "YONO SBI Pay", "ICICI iMobile Pay",
        "UPI", "LinkAja", "SeaMoney", "TrueMoney", "AirAsia Pay",
        "Boost Malaysia", "Tencent Pay",
    ],
    "🌍 Africa": [
        "Paystack", "Flutterwave", "M-Pesa", "Paga", "Moov Africa",
        "Remitly", "WorldRemit",
    ],
    "🌎 Latin America": [
        "Mercado Pago", "PagSeguro", "Stone", "Uala", "PIX",
        "Boleto", "EBANX", "dLocal",
    ],
    "🇸🇦 Middle East": [
        "Ziina", "MyFatoorah", "Hala Pay",
    ],
    "💰 BNPL": [
        "Klarna", "Affirm", "Afterpay", "Sezzle", "Zip", "Clearpay", "Zip Pay",
    ],
    "💳 Wallets": [
        "Apple Pay", "Google Pay", "Samsung Pay", "Amazon Pay", "Venmo",
    ],
    "₿ Crypto": [
        "Coinbase Commerce", "BTCPay", "BitPay", "Binance Pay",
        "NOWPayments", "CoinGate", "Haveno", "Zcash Payments",
    ],
    "📦 Subscription": [
        "Stripe Billing", "Recurly", "Chargebee", "Paddle",
        "Gumroad", "FastSpring", "Zuora",
    ],
    "🏦 Open Banking": [
        "Plaid", "TrueLayer", "GoCardless", "Finicity", "Yodlee",
    ],
    "🎮 Gaming & SaaS": [
        "Xsolla", "Unity Monetization", "Sage Intacct",
        "SAP Concur", "Oracle Payments", "Mindbody", "ClassPass",
    ],
    "⚡ Fintech": [
        "Airwallex", "Marqeta", "Sift Science", "Bolt",
    ],
    "🛒 E-Commerce": [
        "Shopify Payments", "WooCommerce",
    ],
}


def _categorize_gateway(name: str) -> str:
    """Find the category for a gateway name. Returns category key or empty string."""
    for category, gateways in GATEWAY_CATEGORIES.items():
        if name in gateways:
            return category
    return ""


# =============================================================================
# P0-1: CONFIDENCE TIER FORMATTING
# =============================================================================

def format_gateways_with_confidence(
    gateway_matches: Dict[str, 'GatewayMatch']
) -> str:
    """
    Format gateways with confidence tiers, categories, and percentages.
    
    Shows:
    - Confidence emoji (🟢 HIGH, 🟡 MEDIUM, 🔴 LOW)
    - Confidence percentage
    - Detection category (SDK, Form, Header, Word, etc.)
    
    Args:
        gateway_matches: Dict of GatewayMatch objects from analyze_url_response
        
    Returns:
        Formatted string with confidence-aware gateway display
    """
    if not gateway_matches:
        return "❌ None detected"
    
    # Sort by confidence (highest first)
    sorted_matches = sorted(
        gateway_matches.values(),
        key=lambda m: -m.confidence
    )
    
    # Group by confidence tier
    high = [m for m in sorted_matches if m.confidence >= 0.95]
    medium = [m for m in sorted_matches if 0.70 <= m.confidence < 0.95]
    low = [m for m in sorted_matches if m.confidence < 0.70]
    
    # Category badge mapping
    cat_emoji = {
        "SDK": "📦",
        "Form": "📝",
        "Header": "📡",
        "HTML Structure": "🌐",
        "Word": "🔍",
    }
    
    lines: List[str] = []
    
    if high:
        lines.append("🟢 HIGH CONFIDENCE (95%+)")
        for m in high:
            badge = cat_emoji.get(m.category, "•")
            lines.append(f"  {badge} {m.name} ({m.confidence:.0%})")
    
    if medium:
        if lines:
            lines.append("")
        lines.append("🟡 MEDIUM CONFIDENCE (70-94%)")
        for m in medium:
            badge = cat_emoji.get(m.category, "•")
            lines.append(f"  {badge} {m.name} ({m.confidence:.0%})")
    
    if low:
        if lines:
            lines.append("")
        lines.append("🔴 LOW CONFIDENCE (<70%)")
        for m in low:
            badge = cat_emoji.get(m.category, "•")
            lines.append(f"  {badge} {m.name} ({m.confidence:.0%})")
    
    return "\n".join(lines)


def format_gateways_by_category(
    gateway_matches: Dict[str, 'GatewayMatch']
) -> str:
    """
    Group detected gateways by regional/type category with confidence tiers.
    
    Shows each confidence tier, with gateways organized by category within each tier.
    
    Args:
        gateway_matches: Dict of GatewayMatch objects
        
    Returns:
        Formatted string with categorized, confidence-aware gateway display
    """
    if not gateway_matches:
        return "❌ None detected"
    
    # Build category -> matches mapping
    categorized: Dict[str, List] = {}
    uncategorized: List = []
    
    for name, match in gateway_matches.items():
        cat = _categorize_gateway(name)
        if cat:
            categorized.setdefault(cat, []).append((name, match))
        else:
            uncategorized.append((name, match))
    
    # Sort each category's matches by confidence descending
    for cat in categorized:
        categorized[cat].sort(key=lambda x: -x[1].confidence)
    uncategorized.sort(key=lambda x: -x[1].confidence)
    
    # Group into confidence tiers
    def _tier_items(items, lo, hi):
        return [(n, m) for n, m in items if lo <= m.confidence < hi]
    
    all_items = [(n, m) for lst in categorized.values() for n, m in lst] + uncategorized
    
    high_items = [(n, m) for n, m in all_items if m.confidence >= 0.95]
    med_items = [(n, m) for n, m in all_items if 0.70 <= m.confidence < 0.95]
    low_items = [(n, m) for n, m in all_items if m.confidence < 0.70]
    
    lines: List[str] = []
    
    def _render_tier(items, tier_label):
        if not items:
            return
        if lines:
            lines.append("")
        lines.append(tier_label)
        # Group items by category within this tier
        by_cat: Dict[str, List] = {}
        other: List = []
        for n, m in items:
            cat = _categorize_gateway(n)
            if cat:
                by_cat.setdefault(cat, []).append((n, m))
            else:
                other.append((n, m))
        for cat, cat_items in by_cat.items():
            lines.append(f"  {cat}")
            for n, m in sorted(cat_items, key=lambda x: -x[1].confidence):
                lines.append(f"    • {n} {m.confidence:.0%}")
        if other:
            lines.append("  📦 Other")
            for n, m in sorted(other, key=lambda x: -x[1].confidence):
                lines.append(f"    • {n} {m.confidence:.0%}")
    
    _render_tier(high_items, "🟢 HIGH CONFIDENCE (95%+)")
    _render_tier(med_items, "🟡 MEDIUM CONFIDENCE (70-94%)")
    _render_tier(low_items, "🔴 LOW CONFIDENCE (<70%)")
    
    return "\n".join(lines)


# =============================================================================
# P2-2: RICH ERROR MESSAGES WITH RECOVERY SUGGESTIONS
# =============================================================================

def format_error_result(
    url: str,
    status_code: int,
    security_type: str = "N/A",
) -> str:
    """
    Format error result with diagnosis and actionable recovery suggestions.
    
    Args:
        url: The URL that was scanned
        status_code: HTTP status code (or error-indicator code)
        security_type: The security_type string from check_url (may contain error info)
        
    Returns:
        Formatted error string with diagnosis and suggestions
    """
    display_url = url if len(url) <= 50 else url[:47] + "..."
    
    # Determine diagnosis and suggestions based on status code / error string
    sec_lower = security_type.lower()
    
    if status_code == 403 or "forbidden" in sec_lower:
        diagnosis = "🟠 403 Access Denied"
        suggestions = (
            "💡 This site may block automated scanning.\n"
            "\n"
            "Try:\n"
            "  • Disable VPN/proxy if using one\n"
            "  • Wait a few minutes and retry\n"
            "  • The site may have WAF/anti-bot protection"
        )
    elif status_code == 429 or "rate limit" in sec_lower:
        diagnosis = "🟠 429 Rate Limited"
        suggestions = (
            "💡 Too many requests to this site.\n"
            "\n"
            "Try:\n"
            "  • Wait a few minutes before rescanning\n"
            "  • Use /bulk for batch scans (better throttling)\n"
            "  • Reduce number of URLs per request"
        )
    elif status_code == 404 or "not found" in sec_lower:
        diagnosis = "🔴 404 Not Found"
        suggestions = (
            "💡 The URL doesn't exist or is incorrect.\n"
            "\n"
            "Try:\n"
            "  • Check the URL spelling\n"
            "  • Use full URL with https://\n"
            "  • Check if the domain is still active"
        )
    elif status_code == 408 or "timeout" in sec_lower:
        diagnosis = "🔴 Request Timeout"
        suggestions = (
            "💡 The site took too long to respond.\n"
            "\n"
            "Try:\n"
            "  • Check if the site is online\n"
            "  • Try again in a few minutes\n"
            "  • The server may be under heavy load"
        )
    elif status_code == 400 or "bad request" in sec_lower:
        diagnosis = "🟠 400 Bad Request"
        suggestions = (
            "💡 The server rejected the request format.\n"
            "\n"
            "Try:\n"
            "  • Check the URL format\n"
            "  • CDN/WAF may be blocking\n"
            "  • Server may require authentication"
        )
    elif status_code == 503 or "connection error" in sec_lower or "circuit open" in sec_lower:
        if "circuit open" in sec_lower:
            diagnosis = "🔴 Circuit Open"
            suggestions = (
                "💡 This domain has been failing repeatedly.\n"
                "\n"
                "The circuit breaker has temporarily\n"
                "blocked requests to protect performance.\n"
                "\n"
                "Try:\n"
                "  • Wait for the cooldown to expire\n"
                "  • Check if the site is online"
            )
        elif "dns" in sec_lower or "resolve" in sec_lower:
            diagnosis = "🔴 DNS Resolution Failed"
            suggestions = (
                "💡 Domain name couldn't be resolved.\n"
                "\n"
                "Try:\n"
                "  • Check if the domain exists\n"
                "  • Check for typos in the URL\n"
                "  • The domain may have expired"
            )
        else:
            diagnosis = "🔴 Connection Failed"
            suggestions = (
                "💡 Cannot connect to the site.\n"
                "\n"
                "Try:\n"
                "  • Check if the site is online\n"
                "  • Try a different URL\n"
                "  • The server may be down"
            )
    elif status_code == 400 and "invalid url" in sec_lower:
        diagnosis = "🔴 Invalid URL"
        suggestions = (
            "💡 The URL format is not valid.\n"
            "\n"
            "Try:\n"
            "  • Use format: /url https://example.com\n"
            "  • Include the full domain name\n"
            "  • Avoid special characters"
        )
    elif status_code >= 500:
        diagnosis = f"🔴 {status_code} Server Error"
        suggestions = (
            "💡 The website's server encountered an error.\n"
            "\n"
            "This is a problem on their end.\n"
            "\n"
            "Try:\n"
            "  • Wait and retry in a few minutes\n"
            "  • Check if the site works in your browser"
        )
    else:
        diagnosis = f"🔴 Error ({status_code})"
        suggestions = (
            "💡 An unexpected error occurred.\n"
            "\n"
            "Try:\n"
            "  • Check the URL\n"
            "  • Try again in a few minutes"
        )
    
    return (
        f"╭─ SCAN RESULT ─────────────╮\n"
        f"│  🌐 {display_url}\n"
        f"│  {diagnosis}\n"
        f"╰───────────────────────────╯\n"
        f"\n"
        f"┌─ ❌ ERROR DETAILS ─────────\n"
        f"│\n"
        f"│  {security_type[:80]}\n"
        f"│\n"
        f"└────────────────────────────\n"
        f"\n"
        f"{suggestions}\n\n"
    )


# =============================================================================
# P2-1: BULK SCAN SUMMARY DASHBOARD
# =============================================================================

def format_bulk_summary(
    total_urls: int,
    successful: int,
    failed: int,
    gateway_counts: Dict[str, int],
    scan_duration_ms: float,
) -> str:
    """
    Format bulk scan summary dashboard with top gateways and timing.
    
    Shows:
    - Success rate with visual indicator
    - Top 10 gateways with frequency bar chart
    - Scan timing
    
    Args:
        total_urls: Total URLs in the scan
        successful: Number of successfully scanned URLs
        failed: Number of failed URLs
        gateway_counts: Dict mapping gateway name -> count
        scan_duration_ms: Total scan duration in milliseconds
        
    Returns:
        Formatted dashboard string
    """
    success_rate = (successful / total_urls * 100) if total_urls > 0 else 0
    
    # Top 10 gateways
    top_gateways = sorted(gateway_counts.items(), key=lambda x: -x[1])[:10]
    max_count = max(gateway_counts.values()) if gateway_counts else 1
    
    summary = (
        "╭─ 📊 BULK SCAN SUMMARY ────╮\n"
        "│\n"
        f"│  📈 Results\n"
        f"│    • Total URLs    ›  {total_urls}\n"
        f"│    • ✅ Successful ›  {successful} ({success_rate:.1f}%)\n"
        f"│    • ❌ Failed     ›  {failed}\n"
        f"│\n"
        f"│  🔍 Unique Gateways Found\n"
        f"│    • {len(gateway_counts)} different gateways\n"
    )
    
    if top_gateways:
        summary += "│\n│  🏆 Top Gateways\n"
        for i, (gateway, count) in enumerate(top_gateways, 1):
            bar_len = int(count / max_count * 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            gw_display = gateway[:18]
            summary += f"│    {i:2}. {gw_display:<20} {bar} {count}\n"
    
    # Timing
    minutes = int(scan_duration_ms / 60000)
    seconds = int((scan_duration_ms % 60000) / 1000)
    summary += f"│\n│  ⏱️  Duration: {minutes}m {seconds}s\n"
    
    summary += (
        "│\n"
        "│  📥 Results saved to file (see attachment)\n"
        "│\n"
        "╰───────────────────────────╯"
    )
    
    return summary


# =============================================================================
# MAIN OUTPUT FORMATTER — Enhanced with confidence + metadata
# =============================================================================

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
    cart_abandonment: str = "None detected",
    gateway_matches: Optional[Dict[str, 'GatewayMatch']] = None,
    scan_duration_ms: Optional[float] = None,
    cache_hit: bool = False,
) -> str:
    """
    Format the URL check result into a readable message.

    Uses a modern card-based design with rounded corners, chevron bullets,
    and proper vertical spacing for improved readability.

    Now includes:
    - P0-1: Confidence tier display when gateway_matches is provided
    - P0-3: Scan metadata footer (duration, cache hit)

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
        gateway_matches: Optional dict of GatewayMatch objects for confidence display
        scan_duration_ms: Optional scan duration in milliseconds
        cache_hit: Whether this result was served from cache

    Returns:
        str: Formatted result string (plain text, no Markdown)
    """
    # For error results, use the rich error formatter
    if not detected_gateways and status_code not in (200, 301, 302, 303, 307, 308):
        return format_error_result(url, status_code, payment_security_type)
    
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

    # P0-1: Use confidence-aware gateway display if gateway_matches available
    if gateway_matches:
        gateways_str = format_gateways_with_confidence(gateway_matches)
    elif detected_gateways:
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

    # Build the gateway section — multi-line for confidence display
    if gateway_matches and detected_gateways:
        gateway_lines = "\n".join(f"│  {line}" for line in gateways_str.split("\n"))
    else:
        gateway_lines = f"│  {gateways_str}"

    # P0-3: Build metadata footer
    metadata_section = ""
    metadata_lines = []
    
    if scan_duration_ms is not None:
        if scan_duration_ms < 500:
            speed_emoji = "⚡"
        elif scan_duration_ms < 1000:
            speed_emoji = "🚀"
        elif scan_duration_ms < 3000:
            speed_emoji = "🐢"
        else:
            speed_emoji = "🔄"
        metadata_lines.append(f"│  Duration   ›  {speed_emoji} {scan_duration_ms:.0f}ms")
    
    if cache_hit:
        metadata_lines.append("│  Cache      ›  ✅ HIT (instant)")
    elif scan_duration_ms is not None:
        metadata_lines.append("│  Cache      ›  ❌ MISS (fresh scan)")
    
    if metadata_lines:
        metadata_section = (
            "\n"
            "┌─ ⚡ SCAN INFO ─────────────\n"
            "│\n"
            + "\n".join(metadata_lines) + "\n"
            "│\n"
            "└────────────────────────────\n"
        )

    return (
        f"╭─ SCAN RESULT ─────────────╮\n"
        f"│  🌐 {display_url}\n"
        f"│  {status_display}\n"
        f"╰───────────────────────────╯\n"
        f"\n"
        f"┌─ 💳 GATEWAYS ──────────────\n"
        f"│\n"
        f"{gateway_lines}\n"
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
        f"└────────────────────────────\n"
        + metadata_section
        + "\n"
    )
