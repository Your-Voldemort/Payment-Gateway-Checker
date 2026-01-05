"""
Optimized payment gateway detection module.

This module provides improved detection accuracy through:
1. Word boundary regex matching to avoid false positives
2. JavaScript SDK pattern detection for modern payment forms
3. Confidence scoring to prioritize high-value matches
4. Structured pattern categories for better organization
5. BeautifulSoup HTML parsing for structured element analysis (Part 3.2)
"""
import re
from typing import Dict, List, Tuple, NamedTuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
from logger import setup_logger

logger = setup_logger()

# Import HTML parser module for structured analysis
# Provides BeautifulSoup-based structured element detection (Part 3.2)
HTML_PARSER_AVAILABLE = False
parse_html_structure = None
detect_gateways_from_html_structure = None
detect_inbuilt_payment_from_structure = None
get_payment_form_details = None
HTMLStructure = None

try:
    from html_parser import (
        parse_html_structure as _parse_html_structure,
        detect_gateways_from_html_structure as _detect_gateways,
        detect_inbuilt_payment_from_structure as _detect_inbuilt,
        get_payment_form_details as _get_form_details,
        BS4_AVAILABLE,
        HTMLStructure as _HTMLStructure,
    )
    if BS4_AVAILABLE:
        HTML_PARSER_AVAILABLE = True
        parse_html_structure = _parse_html_structure
        detect_gateways_from_html_structure = _detect_gateways
        detect_inbuilt_payment_from_structure = _detect_inbuilt
        get_payment_form_details = _get_form_details
        HTMLStructure = _HTMLStructure
        logger.info("Structured HTML parsing enabled (BeautifulSoup available)")
    else:
        logger.warning("BeautifulSoup not installed. Structured HTML parsing disabled.")
except ImportError:
    logger.warning("HTML parser module not available. Structured analysis disabled.")


class ConfidenceLevel(Enum):
    """Detection confidence levels."""
    HIGH = 0.95      # Script includes, SDK initialization
    MEDIUM = 0.70    # Form attributes, specific patterns
    LOW = 0.40       # Word mentions with boundaries
    VERY_LOW = 0.20  # Generic mentions (prone to false positives)


@dataclass
class GatewayMatch:
    """Represents a detected payment gateway with confidence."""
    name: str
    confidence: float
    evidence: str
    category: str


# =============================================================================
# HIGH CONFIDENCE PATTERNS - JavaScript SDK includes and initialization
# =============================================================================
# These patterns match specific CDN URLs and SDK initialization code.
# False positive rate: < 1%

SDK_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
    # Stripe
    "Stripe": [
        (r'js\.stripe\.com/v\d+', 0.98),
        (r'Stripe\s*\(\s*[\'"][pk]_(?:live|test)_[^\'"]+[\'\"]', 0.99),
        (r'stripe\.elements\s*\(', 0.95),
        (r'stripe-card-element', 0.90),
        (r'data-stripe-key', 0.95),
        (r'StripeCheckout\.configure', 0.98),
    ],
    # PayPal
    "PayPal": [
        (r'paypal\.com/sdk/js', 0.98),
        (r'paypal\.Buttons\s*\(', 0.98),
        (r'paypalobjects\.com', 0.90),
        (r'data-paypal-button', 0.90),
        (r'paypal-button-container', 0.85),
    ],
    # Braintree (PayPal)
    "Braintree": [
        (r'js\.braintreegateway\.com', 0.98),
        (r'braintree\.client\.create', 0.98),
        (r'braintree-web', 0.85),
        (r'braintree\.hostedFields', 0.95),
    ],
    # Square
    "Square": [
        (r'js\.squareup\.com', 0.98),
        (r'squarecdn\.com/js', 0.95),
        (r'SqPaymentForm', 0.98),
        (r'sq-payment-form', 0.90),
    ],
    # Adyen
    "Adyen": [
        (r'checkoutshopper.*\.adyen\.com', 0.98),
        (r'AdyenCheckout', 0.98),
        (r'adyen-checkout', 0.90),
        (r'adyen\.com/checkoutshopper', 0.95),
    ],
    # Razorpay
    "Razorpay": [
        (r'checkout\.razorpay\.com', 0.98),
        (r'Razorpay\s*\(', 0.98),
        (r'razorpay\.js', 0.90),
        (r'data-razorpay', 0.90),
    ],
    # Klarna
    "Klarna": [
        (r'x\.klarnacdn\.net', 0.98),
        (r'klarna\.com/checkout', 0.95),
        (r'Klarna\.Payments', 0.98),
        (r'klarna-widget', 0.90),
    ],
    # Affirm
    "Affirm": [
        (r'cdn\d*\.affirm\.com', 0.98),
        (r'affirm\.js', 0.90),
        (r'AffirmUI', 0.95),
        (r'data-affirm', 0.90),
    ],
    # Afterpay/Clearpay
    "Afterpay": [
        (r'static\.afterpay\.com', 0.98),
        (r'afterpay\.js', 0.90),
        (r'afterpay-widget', 0.90),
    ],
    # Checkout.com
    "Checkout.com": [
        (r'cdn\.checkout\.com/js', 0.98),
        (r'Frames\.init', 0.98),
        (r'cko-card-number', 0.90),
    ],
    # Mollie
    "Mollie": [
        (r'js\.mollie\.com', 0.98),
        (r'mollie\.Components', 0.95),
        (r'molliecdn', 0.90),
    ],
    # Recurly
    "Recurly": [
        (r'js\.recurly\.com', 0.98),
        (r'recurly\.configure', 0.98),
    ],
    # Chargebee
    "Chargebee": [
        (r'js\.chargebee\.com', 0.98),
        (r'Chargebee\.init', 0.98),
    ],
    # Google Pay
    "Google Pay": [
        (r'pay\.google\.com/gp/p/js/pay\.js', 0.98),
        (r'google\.payments\.api', 0.95),
        (r'GooglePayButton', 0.90),
        (r'gpay-button', 0.85),
    ],
    # Apple Pay
    "Apple Pay": [
        (r'ApplePaySession', 0.98),
        (r'apple-pay-button', 0.90),
        (r'apple-pay-logo', 0.80),
    ],
    # Authorize.Net
    "Authorize.Net": [
        (r'js\.authorize\.net', 0.98),
        (r'jstest\.authorize\.net', 0.95),
        (r'Accept\.dispatchData', 0.98),
        (r'AcceptCore', 0.90),
    ],
    # Paytm
    "Paytm": [
        (r'securegw\.paytm\.in', 0.98),
        (r'merchantpgpui\.paytm\.in', 0.95),
        (r'paytmcdn', 0.85),
    ],
    # PayStack (Africa)
    "Paystack": [
        (r'js\.paystack\.co', 0.98),
        (r'PaystackPop', 0.98),
        (r'paystack-button', 0.90),
    ],
    # Flutterwave (Africa)
    "Flutterwave": [
        (r'checkout\.flutterwave\.com', 0.98),
        (r'FlutterwaveCheckout', 0.98),
        (r'flw-inline', 0.90),
    ],
    # 2Checkout/Verifone
    "2Checkout": [
        (r'2checkout\.com/checkout', 0.95),
        (r'verifone\.cloud', 0.90),
    ],
    # Worldpay
    "Worldpay": [
        (r'worldpay\.com', 0.85),
        (r'worldpay\.js', 0.90),
    ],
    # CyberSource
    "CyberSource": [
        (r'cybersource\.com', 0.85),
        (r'flex-microform', 0.95),
    ],
    # Paddle
    "Paddle": [
        (r'cdn\.paddle\.com', 0.98),
        (r'paddle\.js', 0.95),
        (r'Paddle\.Setup', 0.98),
    ],
    # Gumroad
    "Gumroad": [
        (r'gumroad\.com/js', 0.95),
        (r'gumroad-overlay', 0.90),
    ],
    # Sezzle
    "Sezzle": [
        (r'widget\.sezzle\.com', 0.98),
        (r'sezzle-widget', 0.90),
    ],
    # Zip (Quadpay)
    "Zip": [
        (r'zip\.co', 0.80),
        (r'quadpay', 0.85),
    ],
    # Mercado Pago
    "Mercado Pago": [
        (r'sdk\.mercadopago\.com', 0.98),
        (r'MercadoPago', 0.95),
    ],
    # EBANX
    "EBANX": [
        (r'ebanx\.com', 0.85),
        (r'ebanxpay', 0.90),
    ],
    # dLocal
    "dLocal": [
        (r'dlocal\.com', 0.85),
    ],
    # Alipay
    "Alipay": [
        (r'alipay\.com', 0.80),
        (r'alipayobjects\.com', 0.90),
    ],
    # WeChat Pay
    "WeChat Pay": [
        (r'wx\.qq\.com', 0.80),
        (r'wxpay', 0.85),
        (r'wechatpay', 0.90),
    ],
    # GoCashless / Plaid
    "Plaid": [
        (r'cdn\.plaid\.com', 0.98),
        (r'link\.plaid\.com', 0.95),
        (r'Plaid\.create', 0.98),
    ],
    # GoCardless
    "GoCardless": [
        (r'gocardless\.com', 0.85),
        (r'gc\.js', 0.90),
    ],
    # Shopify Payments
    "Shopify Payments": [
        (r'shop\.app', 0.70),
        (r'shopify\.com/payments', 0.85),
        (r'shop-pay-button', 0.90),
    ],
    # WooCommerce
    "WooCommerce": [
        (r'woocommerce', 0.70),
        (r'wc-payment', 0.85),
    ],
}


# =============================================================================
# MEDIUM CONFIDENCE PATTERNS - Form attributes and specific identifiers
# =============================================================================
# These patterns match HTML attributes that strongly suggest payment integration

FORM_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
    "Stripe": [
        (r'data-stripe', 0.80),
        (r'stripe-element', 0.75),
    ],
    "PayPal": [
        (r'data-paypal', 0.80),
        (r'paypal-buttons', 0.75),
    ],
    "Square": [
        (r'sq-card', 0.80),
    ],
    "Braintree": [
        (r'data-braintree', 0.80),
    ],
}


# =============================================================================
# WORD BOUNDARY PATTERNS - Gateway names with word boundaries
# =============================================================================
# Uses \b to prevent substring matches like "stripe" in "pinstripe"

WORD_BOUNDARY_GATEWAYS: List[Tuple[str, str, float]] = [
    # (regex pattern, display name, confidence)
    # Major Global
    (r'\bstripe\b', 'Stripe', 0.40),
    (r'\bpaypal\b', 'PayPal', 0.40),
    (r'\bbraintree\b', 'Braintree', 0.40),
    (r'\bsquare\b', 'Square', 0.30),  # Lower - common word
    (r'\badyen\b', 'Adyen', 0.45),
    (r'\bauthorize\.?net\b', 'Authorize.Net', 0.45),
    (r'\bcybersource\b', 'CyberSource', 0.45),
    (r'\bworldpay\b', 'Worldpay', 0.45),
    (r'\bcheckout\.com\b', 'Checkout.com', 0.45),

    # BNPL
    (r'\bklarna\b', 'Klarna', 0.45),
    (r'\baffirm\b', 'Affirm', 0.40),
    (r'\bafterpay\b', 'Afterpay', 0.45),
    (r'\bclearpay\b', 'Clearpay', 0.45),
    (r'\bsezzle\b', 'Sezzle', 0.45),
    (r'\bzip\s*pay\b', 'Zip Pay', 0.45),

    # India
    (r'\brazorpay\b', 'Razorpay', 0.50),
    (r'\bpaytm\b', 'Paytm', 0.45),
    (r'\bphonepe\b', 'PhonePe', 0.50),
    (r'\bjuspay\b', 'Juspay', 0.50),
    (r'\bcashfree\b', 'Cashfree', 0.50),
    (r'\bccavenue\b', 'CCAvenue', 0.50),
    (r'\bbilldesk\b', 'Billdesk', 0.50),
    (r'\bupi\b', 'UPI', 0.35),

    # China
    (r'\balipay\b', 'Alipay', 0.45),
    (r'\bwechat\s*pay\b', 'WeChat Pay', 0.45),
    (r'\bunionpay\b', 'UnionPay', 0.50),

    # Africa
    (r'\bpaystack\b', 'Paystack', 0.50),
    (r'\bflutterwave\b', 'Flutterwave', 0.50),
    (r'\bm-?pesa\b', 'M-Pesa', 0.50),

    # Latin America
    (r'\bmercado\s*pago\b', 'Mercado Pago', 0.50),
    (r'\bpagseguro\b', 'PagSeguro', 0.50),
    (r'\bebanx\b', 'EBANX', 0.50),
    (r'\bpix\b', 'PIX', 0.35),
    (r'\bboleto\b', 'Boleto', 0.45),

    # Europe
    (r'\bmollie\b', 'Mollie', 0.50),
    (r'\bideal\b', 'iDEAL', 0.40),
    (r'\bsofort\b', 'Sofort', 0.45),
    (r'\bgiropay\b', 'Giropay', 0.50),
    (r'\bbancontact\b', 'Bancontact', 0.50),
    (r'\btrustly\b', 'Trustly', 0.45),
    (r'\bprzelewy24\b', 'Przelewy24', 0.50),

    # Wallets
    (r'\bapple\s*pay\b', 'Apple Pay', 0.45),
    (r'\bgoogle\s*pay\b', 'Google Pay', 0.45),
    (r'\bsamsung\s*pay\b', 'Samsung Pay', 0.45),
    (r'\bamazon\s*pay\b', 'Amazon Pay', 0.45),
    (r'\bvenmo\b', 'Venmo', 0.45),

    # Subscription
    (r'\brecurly\b', 'Recurly', 0.50),
    (r'\bchargebee\b', 'Chargebee', 0.50),
    (r'\bpaddle\b', 'Paddle', 0.45),
    (r'\bfastspring\b', 'FastSpring', 0.50),
    (r'\bgumroad\b', 'Gumroad', 0.50),

    # Crypto
    (r'\bbitpay\b', 'BitPay', 0.50),
    (r'\bcoinbase\s*commerce\b', 'Coinbase Commerce', 0.50),
    (r'\bnowpayments\b', 'NOWPayments', 0.50),
    (r'\bcoingate\b', 'CoinGate', 0.50),

    # Open Banking
    (r'\bplaid\b', 'Plaid', 0.40),
    (r'\bgocardless\b', 'GoCardless', 0.50),
    (r'\btruelayer\b', 'TrueLayer', 0.50),
]


# =============================================================================
# DETECTION FUNCTIONS
# =============================================================================

# Pre-compile regex patterns for performance
_compiled_sdk_patterns: Dict[str, List[Tuple[re.Pattern, float]]] = {}
_compiled_form_patterns: Dict[str, List[Tuple[re.Pattern, float]]] = {}
_compiled_word_patterns: List[Tuple[re.Pattern, str, float]] = []


def _compile_patterns():
    """Pre-compile all regex patterns for better performance."""
    global _compiled_sdk_patterns, _compiled_form_patterns, _compiled_word_patterns

    if _compiled_sdk_patterns:
        return  # Already compiled

    # Compile SDK patterns
    for gateway, patterns in SDK_PATTERNS.items():
        _compiled_sdk_patterns[gateway] = [
            (re.compile(pattern, re.IGNORECASE), conf)
            for pattern, conf in patterns
        ]

    # Compile form patterns
    for gateway, patterns in FORM_PATTERNS.items():
        _compiled_form_patterns[gateway] = [
            (re.compile(pattern, re.IGNORECASE), conf)
            for pattern, conf in patterns
        ]

    # Compile word boundary patterns
    _compiled_word_patterns = [
        (re.compile(pattern, re.IGNORECASE), name, conf)
        for pattern, name, conf in WORD_BOUNDARY_GATEWAYS
    ]

    logger.debug("Detection patterns compiled")


def find_payment_gateways_optimized(html: str) -> Tuple[List[str], Dict[str, GatewayMatch]]:
    """
    Detect payment gateways with improved accuracy using multi-tier matching.

    This function uses three tiers of pattern matching:
    1. HIGH: JavaScript SDK includes and initialization (98%+ confidence)
    2. MEDIUM: Form attributes and specific identifiers (70-85% confidence)
    3. LOW: Word boundary matches (40-50% confidence)

    Args:
        html: The HTML content to analyze

    Returns:
        Tuple of (gateway_names_list, detailed_matches_dict)
        - gateway_names_list: Simple list of detected gateway names (for backward compatibility)
        - detailed_matches_dict: Dict mapping gateway name to GatewayMatch with confidence
    """
    _compile_patterns()

    matches: Dict[str, GatewayMatch] = {}

    # Tier 1: High confidence SDK patterns
    for gateway, patterns in _compiled_sdk_patterns.items():
        for pattern, confidence in patterns:
            match = pattern.search(html)
            if match:
                # Keep highest confidence match for each gateway
                if gateway not in matches or matches[gateway].confidence < confidence:
                    matches[gateway] = GatewayMatch(
                        name=gateway,
                        confidence=confidence,
                        evidence=match.group(0)[:50],
                        category="SDK"
                    )

    # Tier 2: Medium confidence form patterns
    for gateway, patterns in _compiled_form_patterns.items():
        for pattern, confidence in patterns:
            if gateway in matches:
                continue  # Already found with higher confidence
            match = pattern.search(html)
            if match:
                matches[gateway] = GatewayMatch(
                    name=gateway,
                    confidence=confidence,
                    evidence=match.group(0)[:50],
                    category="Form"
                )

    # Tier 3: Low confidence word boundary patterns
    for pattern, name, confidence in _compiled_word_patterns:
        if name in matches:
            continue  # Already found with higher confidence
        match = pattern.search(html)
        if match:
            matches[name] = GatewayMatch(
                name=name,
                confidence=confidence,
                evidence=match.group(0)[:50],
                category="Word"
            )

    # Sort by confidence (highest first) and return
    sorted_matches = sorted(matches.values(), key=lambda m: -m.confidence)
    gateway_names = [m.name for m in sorted_matches]

    logger.debug(f"Detected {len(matches)} gateways, highest confidence: "
                 f"{sorted_matches[0].name if sorted_matches else 'none'}")

    return gateway_names, matches


def filter_high_confidence_gateways(
    matches: Dict[str, GatewayMatch],
    min_confidence: float = 0.5
) -> List[str]:
    """
    Filter gateway matches by minimum confidence threshold.

    Args:
        matches: Dictionary of GatewayMatch objects
        min_confidence: Minimum confidence to include (default 0.5)

    Returns:
        List of gateway names meeting the threshold
    """
    return [
        m.name for m in matches.values()
        if m.confidence >= min_confidence
    ]


# =============================================================================
# ENHANCED SECURITY DETECTION
# =============================================================================

# Compiled security patterns
_security_patterns = {
    '3d_secure': [
        re.compile(r'\b3d\s*secure\b', re.IGNORECASE),
        re.compile(r'\bverified\s*by\s*visa\b', re.IGNORECASE),
        re.compile(r'\bmastercard\s*securecode\b', re.IGNORECASE),
        re.compile(r'\bsafekey\b', re.IGNORECASE),  # Amex
        re.compile(r'\bprotectbuy\b', re.IGNORECASE),  # Discover
        re.compile(r'\b3ds\b', re.IGNORECASE),
        re.compile(r'\b3d-?auth', re.IGNORECASE),
    ],
    'otp': [
        re.compile(r'\bone[- ]?time\s*password\b', re.IGNORECASE),
        re.compile(r'\botp\b', re.IGNORECASE),
        re.compile(r'\bverification\s*code\b', re.IGNORECASE),
        re.compile(r'\bsms\s*code\b', re.IGNORECASE),
        re.compile(r'\bauthentication\s*code\b', re.IGNORECASE),
        re.compile(r'\benter\s*the\s*code\b', re.IGNORECASE),
    ],
    'captcha': [
        re.compile(r'\bcaptcha\b', re.IGNORECASE),
        re.compile(r'\brecaptcha\b', re.IGNORECASE),
        re.compile(r'\bhcaptcha\b', re.IGNORECASE),
        re.compile(r'\bturnstile\b', re.IGNORECASE),  # Cloudflare
        re.compile(r'\bprove\s*you\s*are\s*not\s*a\s*robot\b', re.IGNORECASE),
        re.compile(r'\bi\'?m\s*not\s*a\s*robot\b', re.IGNORECASE),
    ],
    'cloudflare': [
        re.compile(r'\bcf-ray\b', re.IGNORECASE),
        re.compile(r'\bcf-request-id\b', re.IGNORECASE),
        re.compile(r'\bcloudflare\b', re.IGNORECASE),
        re.compile(r'\bchecking\s*your\s*browser\b', re.IGNORECASE),
        re.compile(r'\bddos\s*protection\b', re.IGNORECASE),
    ],
}


def check_security_features(html: str, headers: dict = None) -> Dict[str, bool]:
    """
    Check for various security features in the page.

    Args:
        html: HTML content to analyze
        headers: Optional response headers

    Returns:
        Dictionary of security feature -> detected (bool)
    """
    results = {
        '3d_secure': False,
        'otp': False,
        'captcha': False,
        'cloudflare': False,
    }

    # Check HTML patterns
    for feature, patterns in _security_patterns.items():
        for pattern in patterns:
            if pattern.search(html):
                results[feature] = True
                break

    # Check headers for Cloudflare
    if headers:
        if headers.get('cf-ray') or headers.get('cf-request-id'):
            results['cloudflare'] = True
        server = headers.get('server', '').lower()
        if 'cloudflare' in server:
            results['cloudflare'] = True

    return results


# =============================================================================
# CVV/CVC DETECTION
# =============================================================================

_cvv_patterns = [
    re.compile(r'\bcvv\b', re.IGNORECASE),
    re.compile(r'\bcvc\b', re.IGNORECASE),
    re.compile(r'\bcvv2\b', re.IGNORECASE),
    re.compile(r'\bcvc2\b', re.IGNORECASE),
    re.compile(r'\bsecurity\s*code\b', re.IGNORECASE),
    re.compile(r'\bcard\s*verification\b', re.IGNORECASE),
]


def check_cvv_requirement(html: str) -> str:
    """
    Check for CVV/CVC requirements in the page.

    Returns:
        String describing CVV/CVC requirement status
    """
    cvv_found = False
    cvc_found = False

    html_lower = html.lower()

    # Quick string checks first (faster than regex)
    if 'cvv' in html_lower:
        cvv_found = True
    if 'cvc' in html_lower:
        cvc_found = True

    if cvv_found and cvc_found:
        return "Both CVV and CVC Required"
    elif cvv_found:
        return "CVV Required"
    elif cvc_found:
        return "CVC Required"

    # Check for alternative security code mentions (with various separators)
    if re.search(r'\bsecurity[_\-\s]*code\b', html, re.IGNORECASE):
        return "Security Code Required"

    return "No CVV/CVC Requirement Detected"


# =============================================================================
# INBUILT PAYMENT SYSTEM DETECTION
# =============================================================================

_inbuilt_patterns = {
    'card_form': [
        re.compile(r'<input[^>]*name=["\']?card[_-]?number', re.IGNORECASE),
        re.compile(r'<input[^>]*id=["\']?cc[_-]?number', re.IGNORECASE),
        re.compile(r'<input[^>]*autocomplete=["\']?cc-number', re.IGNORECASE),
        re.compile(r'<input[^>]*data-card-number', re.IGNORECASE),
        re.compile(r'id=["\']?creditCardNumber', re.IGNORECASE),
    ],
    'expiry': [
        re.compile(r'<input[^>]*(exp|expir)', re.IGNORECASE),
        re.compile(r'<select[^>]*id=["\']?exp', re.IGNORECASE),
        re.compile(r'autocomplete=["\']?cc-exp', re.IGNORECASE),
    ],
    'cvv_form': [
        re.compile(r'<input[^>]*(cvv|cvc|security.?code)', re.IGNORECASE),
        re.compile(r'autocomplete=["\']?cc-csc', re.IGNORECASE),
    ],
}


def check_inbuilt_payment_system(html: str) -> Tuple[bool, Dict[str, bool]]:
    """
    Detect sites with their own card collection forms (not using third-party SDKs).

    Returns:
        Tuple of (has_inbuilt_payment: bool, components_found: dict)
    """
    components = {
        'card_form': False,
        'expiry': False,
        'cvv_form': False,
    }

    for component, patterns in _inbuilt_patterns.items():
        for pattern in patterns:
            if pattern.search(html):
                components[component] = True
                break

    # Consider inbuilt if at least card number and one other component found
    has_inbuilt = components['card_form'] and (components['expiry'] or components['cvv_form'])

    return has_inbuilt, components


# =============================================================================
# ENHANCED HEADER ANALYSIS
# =============================================================================

# Payment provider header patterns
PAYMENT_HEADER_PATTERNS = {
    'Stripe': [
        ('x-stripe-', None),
        ('stripe-account', None),
    ],
    'PayPal': [
        ('x-paypal-', None),
        ('paypal-debug-id', None),
    ],
    'Adyen': [
        ('x-adyen-', None),
    ],
    'Cloudflare': [
        ('cf-ray', None),
        ('cf-cache-status', None),
        ('cf-request-id', None),
        ('server', 'cloudflare'),
    ],
    'Shopify': [
        ('x-shopify-', None),
        ('x-shardid', None),
    ],
    'Fastly': [
        ('x-served-by', None),
        ('x-cache', None),
        ('fastly-', None),
    ],
    'Akamai': [
        ('x-akamai-', None),
        ('akamai-', None),
    ],
}

# Security header categories
SECURITY_HEADERS = {
    'hsts': 'strict-transport-security',
    'csp': 'content-security-policy',
    'frame_options': 'x-frame-options',
    'xss_protection': 'x-xss-protection',
    'content_type_options': 'x-content-type-options',
    'referrer_policy': 'referrer-policy',
    'permissions_policy': 'permissions-policy',
}


def analyze_response_headers(headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Analyze HTTP response headers for payment providers and security features.

    This function examines headers for:
    1. Payment provider signatures (x-stripe-*, x-paypal-*, etc.)
    2. CDN/Protection services (Cloudflare, Akamai, Fastly)
    3. Security headers (HSTS, CSP, etc.)
    4. Server technology hints

    Args:
        headers: Response headers dictionary (case-insensitive keys)

    Returns:
        Dictionary containing analysis results:
        {
            'payment_hints': List of detected payment providers,
            'protection': Dict of CDN/WAF services detected,
            'security_headers': Dict of present security headers,
            'server': Server header value,
            'technology_hints': List of technology hints
        }
    """
    # Normalize headers to lowercase keys for consistent matching
    normalized = {k.lower(): v for k, v in headers.items()}

    results = {
        'payment_hints': [],
        'protection': {
            'cloudflare': False,
            'akamai': False,
            'fastly': False,
        },
        'security_headers': {},
        'server': normalized.get('server', ''),
        'technology_hints': [],
    }

    # Check for payment provider headers
    for provider, patterns in PAYMENT_HEADER_PATTERNS.items():
        for header_pattern, expected_value in patterns:
            for header_key, header_value in normalized.items():
                if header_pattern in header_key:
                    if expected_value is None or expected_value.lower() in header_value.lower():
                        if provider not in results['payment_hints']:
                            results['payment_hints'].append(provider)

                        # Mark protection services
                        if provider == 'Cloudflare':
                            results['protection']['cloudflare'] = True
                        elif provider == 'Fastly':
                            results['protection']['fastly'] = True
                        elif provider == 'Akamai':
                            results['protection']['akamai'] = True

    # Check server header for Cloudflare
    server = normalized.get('server', '').lower()
    if 'cloudflare' in server:
        results['protection']['cloudflare'] = True
        if 'Cloudflare' not in results['payment_hints']:
            results['payment_hints'].append('Cloudflare')

    # Check security headers
    for name, header_key in SECURITY_HEADERS.items():
        if header_key in normalized:
            results['security_headers'][name] = normalized[header_key]

    # Technology hints from various headers
    tech_headers = ['x-powered-by', 'x-aspnet-version', 'x-generator']
    for tech_header in tech_headers:
        if tech_header in normalized:
            results['technology_hints'].append(normalized[tech_header])

    logger.debug(f"Header analysis: {len(results['payment_hints'])} payment hints, "
                 f"{len(results['security_headers'])} security headers")

    return results


def is_cloudflare_protected(headers: dict, html: str = None) -> bool:
    """
    Determine if a site is protected by Cloudflare.

    Checks multiple signals:
    1. CF-Ray header (most reliable)
    2. Server: cloudflare header
    3. CF-Request-ID header
    4. HTML content (challenge pages)

    Args:
        headers: Response headers
        html: Optional HTML content to check

    Returns:
        True if Cloudflare protection is detected
    """
    normalized = {k.lower(): v for k, v in headers.items()}

    # Header checks (most reliable)
    if 'cf-ray' in normalized:
        return True
    if 'cf-request-id' in normalized:
        return True
    if 'cloudflare' in normalized.get('server', '').lower():
        return True

    # HTML content checks (for challenge pages)
    if html:
        cf_patterns = [
            r'\bcf-ray\b',
            r'\bcloudflare\b',
            r'\bchecking\s+your\s+browser\b',
            r'\bray\s+id\b',
            r'cdn-cgi',
        ]
        for pattern in cf_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                return True

    return False


# =============================================================================
# UNIFIED ANALYSIS FUNCTION
# =============================================================================

def analyze_url_response(
    html: str,
    headers: Dict[str, str],
    status_code: int
) -> Dict[str, Any]:
    """
    Perform comprehensive analysis of a URL response.

    This is the main entry point that combines all detection methods:
    1. Payment gateway detection (SDK, form, word patterns)
    2. Structured HTML parsing for scripts, forms, iframes (Part 3.2)
    3. Security feature detection (3DS, OTP, CAPTCHA)
    4. Header analysis (payment hints, security headers)
    5. CVV/CVC requirement detection
    6. Inbuilt payment system detection

    Args:
        html: Raw HTML content of the page
        headers: HTTP response headers as a dictionary
        status_code: HTTP status code (e.g., 200, 404)

    Returns:
        Dictionary containing:
            - gateways: List[str] - All detected payment gateways
            - high_confidence_gateways: List[str] - Gateways with >50% confidence
            - detailed_matches: Dict[str, GatewayMatch] - Full match details
            - captcha: bool - Whether CAPTCHA was detected
            - cloudflare: bool - Whether Cloudflare protection was detected
            - security_type: str - Security feature description
            - cvv_status: str - CVV/CVC requirement status
            - inbuilt_status: str - Built-in payment system status
            - header_analysis: dict - HTTP header security analysis
    """
    # Gateway detection using regex patterns
    gateway_names, gateway_matches = find_payment_gateways_optimized(html)

    # Structured HTML parsing for enhanced detection (Part 3.2)
    html_structure = None
    structured_detections = {}
    payment_form_details = {}
    
    if HTML_PARSER_AVAILABLE:
        try:
            # Parse HTML structure to extract scripts, forms, iframes
            html_structure = parse_html_structure(html)
            
            # Get gateway detections from structured analysis
            structured_detections = html_structure.detected_gateways
            
            # Merge structured detections with regex detections
            # Structured detections often have higher confidence
            for gateway, confidence in structured_detections.items():
                if gateway not in gateway_matches:
                    gateway_names.append(gateway)
                    gateway_matches[gateway] = GatewayMatch(
                        name=gateway,
                        confidence=confidence,
                        evidence="Structured HTML analysis",
                        category="HTML Structure"
                    )
                elif gateway_matches[gateway].confidence < confidence:
                    # Update with higher confidence from structured analysis
                    gateway_matches[gateway] = GatewayMatch(
                        name=gateway,
                        confidence=confidence,
                        evidence="Structured HTML analysis",
                        category="HTML Structure"
                    )
            
            # Get payment form details for extended results
            payment_form_details = get_payment_form_details(html)
            
            logger.debug(f"Structured analysis: {len(structured_detections)} additional gateways, "
                        f"has_payment_form={html_structure.has_payment_form}")
        except Exception as e:
            logger.warning(f"Structured HTML analysis failed: {e}")

    # Security features
    security = check_security_features(html, headers)

    # Header analysis
    header_analysis = analyze_response_headers(headers)

    # CVV/CVC detection
    cvv_status = check_cvv_requirement(html)

    # Inbuilt payment detection - use structured analysis if available
    if HTML_PARSER_AVAILABLE and html_structure and html_structure.parse_successful:
        # Use structured detection for more accurate inbuilt form detection
        has_inbuilt, inbuilt_components = detect_inbuilt_payment_from_structure(html)
    else:
        # Fall back to regex-based detection
        has_inbuilt, inbuilt_components = check_inbuilt_payment_system(html)

    # Merge header-detected payment hints with gateway detection
    for hint in header_analysis['payment_hints']:
        if hint not in gateway_names and hint not in ['Cloudflare', 'Fastly', 'Akamai']:
            gateway_names.append(hint)
            gateway_matches[hint] = GatewayMatch(
                name=hint,
                confidence=0.75,
                evidence="Header detection",
                category="Header"
            )

    # Determine security type string
    if security['3d_secure'] and security['otp']:
        security_type = "Both 3D Secure and OTP Required"
    elif security['3d_secure']:
        security_type = "3D Secure"
    elif security['otp']:
        security_type = "OTP Required"
    else:
        security_type = "2D (No extra security)"

    if security['captcha']:
        security_type += " | Captcha Detected"
    if security['cloudflare'] or header_analysis['protection']['cloudflare']:
        security_type += " | Protected by Cloudflare"

    # Sort gateway names by confidence (highest first)
    gateway_names = sorted(
        gateway_names,
        key=lambda g: gateway_matches.get(g, GatewayMatch(g, 0, "", "")).confidence,
        reverse=True
    )

    return {
        # Primary results (backward compatible)
        'gateways': gateway_names,
        'status_code': status_code,
        'captcha': security['captcha'],
        'cloudflare': security['cloudflare'] or header_analysis['protection']['cloudflare'],
        'security_type': security_type,
        'cvv_status': cvv_status,
        'inbuilt_status': "Yes" if has_inbuilt else "No",

        # Extended results (new)
        'gateway_matches': gateway_matches,
        'security': security,
        'header_analysis': header_analysis,
        'inbuilt_components': inbuilt_components,
        'high_confidence_gateways': filter_high_confidence_gateways(gateway_matches, 0.7),
        
        # Structured analysis results (Part 3.2)
        'html_structure_available': HTML_PARSER_AVAILABLE and html_structure is not None,
        'structured_detections': structured_detections,
        'payment_form_details': payment_form_details,
        'has_payment_form': payment_form_details.get('has_payment_form', False) if payment_form_details else False,
    }
