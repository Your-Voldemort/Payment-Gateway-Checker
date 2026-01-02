"""
HTML Parser module for structured payment gateway detection.

This module uses BeautifulSoup to parse HTML and extract structured information
about payment-related elements:
- Script sources (CDN URLs for payment SDKs)
- Form elements (payment forms, actions, methods)
- Iframes (embedded payment widgets)
- Meta tags (payment provider hints)
- Input fields (card number, expiry, CVV)

This structured approach provides more accurate detection than regex-only
pattern matching by understanding HTML element context.
"""
import re
from typing import Dict, List, Optional, NamedTuple
from dataclasses import dataclass, field
from logger import setup_logger

logger = setup_logger()

# Try to import BeautifulSoup, gracefully degrade if not available
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup not installed. Structured HTML parsing disabled. "
                   "Install with: pip install beautifulsoup4 lxml")


@dataclass
class ScriptInfo:
    """Information about a script element."""
    src: str
    is_external: bool
    inline_content: Optional[str] = None
    gateway_hint: Optional[str] = None
    confidence: float = 0.0


@dataclass
class FormInfo:
    """Information about a form element."""
    action: str
    method: str
    id: Optional[str] = None
    class_names: List[str] = field(default_factory=list)
    has_card_fields: bool = False
    has_expiry_fields: bool = False
    has_cvv_fields: bool = False
    gateway_hint: Optional[str] = None


@dataclass
class IframeInfo:
    """Information about an iframe element."""
    src: str
    id: Optional[str] = None
    name: Optional[str] = None
    gateway_hint: Optional[str] = None
    confidence: float = 0.0


@dataclass
class InputFieldInfo:
    """Information about an input field."""
    name: Optional[str] = None
    id: Optional[str] = None
    type: str = "text"
    autocomplete: Optional[str] = None
    class_names: List[str] = field(default_factory=list)
    data_attributes: Dict[str, str] = field(default_factory=dict)
    field_type: Optional[str] = None  # 'card_number', 'expiry', 'cvv', etc.


@dataclass
class HTMLStructure:
    """Complete parsed HTML structure for payment detection."""
    scripts: List[ScriptInfo] = field(default_factory=list)
    forms: List[FormInfo] = field(default_factory=list)
    iframes: List[IframeInfo] = field(default_factory=list)
    meta_tags: Dict[str, str] = field(default_factory=dict)
    input_fields: List[InputFieldInfo] = field(default_factory=list)
    
    # Aggregated detection results
    detected_gateways: Dict[str, float] = field(default_factory=dict)
    has_payment_form: bool = False
    has_card_inputs: bool = False
    
    # Parsing metadata
    parse_successful: bool = False
    parse_error: Optional[str] = None


# =============================================================================
# GATEWAY DETECTION PATTERNS FOR HTML ELEMENTS
# =============================================================================

# Script source patterns -> (gateway_name, confidence)
SCRIPT_SRC_PATTERNS: Dict[str, List[tuple]] = {
    # Stripe
    "Stripe": [
        (r'js\.stripe\.com', 0.98),
        (r'stripe\.com/v\d+', 0.95),
    ],
    # PayPal
    "PayPal": [
        (r'paypal\.com/sdk', 0.98),
        (r'paypalobjects\.com', 0.90),
    ],
    # Braintree
    "Braintree": [
        (r'js\.braintreegateway\.com', 0.98),
        (r'braintree-web', 0.85),
    ],
    # Square
    "Square": [
        (r'js\.squareup\.com', 0.98),
        (r'squarecdn\.com', 0.90),
    ],
    # Adyen
    "Adyen": [
        (r'checkoutshopper.*\.adyen\.com', 0.98),
        (r'adyen\.com/checkoutshopper', 0.95),
    ],
    # Razorpay
    "Razorpay": [
        (r'checkout\.razorpay\.com', 0.98),
        (r'razorpay\.com', 0.85),
    ],
    # Klarna
    "Klarna": [
        (r'x\.klarnacdn\.net', 0.98),
        (r'klarna\.com', 0.85),
    ],
    # Affirm
    "Affirm": [
        (r'cdn\d*\.affirm\.com', 0.98),
        (r'affirm\.com/js', 0.90),
    ],
    # Afterpay
    "Afterpay": [
        (r'static\.afterpay\.com', 0.98),
        (r'afterpay\.com', 0.85),
    ],
    # Checkout.com
    "Checkout.com": [
        (r'cdn\.checkout\.com', 0.98),
        (r'checkout\.com/js', 0.95),
    ],
    # Mollie
    "Mollie": [
        (r'js\.mollie\.com', 0.98),
        (r'molliecdn', 0.90),
    ],
    # Recurly
    "Recurly": [
        (r'js\.recurly\.com', 0.98),
    ],
    # Chargebee
    "Chargebee": [
        (r'js\.chargebee\.com', 0.98),
    ],
    # Google Pay
    "Google Pay": [
        (r'pay\.google\.com', 0.95),
    ],
    # Paddle
    "Paddle": [
        (r'cdn\.paddle\.com', 0.98),
        (r'paddle\.com/js', 0.90),
    ],
    # Paystack
    "Paystack": [
        (r'js\.paystack\.co', 0.98),
    ],
    # Flutterwave
    "Flutterwave": [
        (r'checkout\.flutterwave\.com', 0.98),
        (r'flutterwave\.com', 0.85),
    ],
    # Mercado Pago
    "Mercado Pago": [
        (r'sdk\.mercadopago\.com', 0.98),
        (r'mercadopago\.com', 0.80),
    ],
    # Authorize.Net
    "Authorize.Net": [
        (r'js\.authorize\.net', 0.98),
        (r'jstest\.authorize\.net', 0.95),
    ],
    # Plaid
    "Plaid": [
        (r'cdn\.plaid\.com', 0.98),
        (r'link\.plaid\.com', 0.95),
    ],
    # Paytm
    "Paytm": [
        (r'securegw\.paytm\.in', 0.98),
        (r'paytm\.in', 0.80),
    ],
    # Sezzle
    "Sezzle": [
        (r'widget\.sezzle\.com', 0.98),
        (r'sezzle\.com', 0.85),
    ],
    # Gumroad
    "Gumroad": [
        (r'gumroad\.com/js', 0.95),
        (r'gumroad\.com', 0.80),
    ],
}

# Iframe source patterns -> (gateway_name, confidence)
IFRAME_SRC_PATTERNS: Dict[str, List[tuple]] = {
    "Stripe": [
        (r'js\.stripe\.com', 0.98),
        (r'checkout\.stripe\.com', 0.98),
    ],
    "PayPal": [
        (r'paypal\.com', 0.90),
        (r'paypalobjects\.com', 0.85),
    ],
    "Braintree": [
        (r'braintreegateway\.com', 0.95),
        (r'braintree-api', 0.90),
    ],
    "Square": [
        (r'squareup\.com', 0.90),
        (r'squareupsandbox\.com', 0.90),
    ],
    "Adyen": [
        (r'adyen\.com', 0.90),
    ],
    "Checkout.com": [
        (r'checkout\.com', 0.90),
    ],
    "Klarna": [
        (r'klarna\.com', 0.90),
        (r'klarnacdn\.net', 0.90),
    ],
    "Apple Pay": [
        (r'apple\.com', 0.75),
    ],
}

# Input field patterns for payment form detection
CARD_NUMBER_PATTERNS = [
    r'card[_-]?number',
    r'cc[_-]?number',
    r'credit[_-]?card',
    r'cardnumber',
    r'pan',
]

EXPIRY_PATTERNS = [
    r'exp',
    r'expir',
    r'cc[_-]?exp',
    r'card[_-]?expir',
    r'valid',
]

CVV_PATTERNS = [
    r'cvv',
    r'cvc',
    r'csc',
    r'security[_-]?code',
    r'card[_-]?code',
    r'verification[_-]?code',
]

# Autocomplete values that indicate payment fields
PAYMENT_AUTOCOMPLETE_VALUES = {
    'card_number': ['cc-number', 'card-number'],
    'expiry': ['cc-exp', 'cc-exp-month', 'cc-exp-year'],
    'cvv': ['cc-csc', 'cc-cvv', 'cc-cvc'],
    'cardholder': ['cc-name', 'cardholder-name'],
}


# =============================================================================
# HTML PARSING FUNCTIONS
# =============================================================================

def parse_html_structure(html: str) -> HTMLStructure:
    """
    Parse HTML content and extract structured payment-related information.
    
    This function extracts:
    - Script elements (external sources and inline content)
    - Form elements with their structure
    - Iframe elements (embedded payment widgets)
    - Meta tags
    - Input fields with payment-related attributes
    
    Args:
        html: Raw HTML content to parse
        
    Returns:
        HTMLStructure dataclass with all parsed information
    """
    structure = HTMLStructure()
    
    if not BS4_AVAILABLE:
        structure.parse_error = "BeautifulSoup not installed"
        return structure
    
    try:
        # Use lxml parser for speed, fall back to html.parser
        try:
            soup = BeautifulSoup(html, 'lxml')
        except Exception:
            soup = BeautifulSoup(html, 'html.parser')
        
        # Extract script elements
        structure.scripts = _extract_scripts(soup)
        
        # Extract form elements
        structure.forms = _extract_forms(soup)
        
        # Extract iframe elements
        structure.iframes = _extract_iframes(soup)
        
        # Extract meta tags
        structure.meta_tags = _extract_meta_tags(soup)
        
        # Extract input fields
        structure.input_fields = _extract_input_fields(soup)
        
        # Aggregate gateway detections from all elements
        structure.detected_gateways = _aggregate_gateway_detections(structure)
        
        # Check if there's a payment form
        structure.has_payment_form = any(f.has_card_fields for f in structure.forms)
        structure.has_card_inputs = any(
            inp.field_type == 'card_number' for inp in structure.input_fields
        )
        
        structure.parse_successful = True
        
        logger.debug(f"HTML parsed: {len(structure.scripts)} scripts, "
                     f"{len(structure.forms)} forms, {len(structure.iframes)} iframes, "
                     f"{len(structure.detected_gateways)} gateways detected")
        
    except Exception as e:
        structure.parse_error = str(e)
        logger.error(f"HTML parsing error: {e}")
    
    return structure


def _extract_scripts(soup) -> List[ScriptInfo]:
    """Extract script elements and analyze for payment SDKs."""
    scripts = []
    
    for script in soup.find_all('script'):
        src = script.get('src', '')
        
        if src:
            # External script
            info = ScriptInfo(
                src=src,
                is_external=True,
                inline_content=None
            )
            
            # Check against known SDK patterns
            for gateway, patterns in SCRIPT_SRC_PATTERNS.items():
                for pattern, confidence in patterns:
                    if re.search(pattern, src, re.IGNORECASE):
                        info.gateway_hint = gateway
                        info.confidence = max(info.confidence, confidence)
                        break
                if info.gateway_hint:
                    break
            
            scripts.append(info)
        else:
            # Inline script - check for SDK initialization patterns
            inline_content = script.string or ''
            if inline_content and len(inline_content) < 10000:  # Limit size
                info = ScriptInfo(
                    src='',
                    is_external=False,
                    inline_content=inline_content[:500]  # Truncate for storage
                )
                
                # Check for common SDK initialization patterns
                sdk_init_patterns = [
                    (r'Stripe\s*\(', 'Stripe', 0.95),
                    (r'stripe\.elements\s*\(', 'Stripe', 0.95),
                    (r'paypal\.Buttons\s*\(', 'PayPal', 0.95),
                    (r'braintree\.client\.create', 'Braintree', 0.95),
                    (r'AdyenCheckout', 'Adyen', 0.95),
                    (r'SqPaymentForm', 'Square', 0.95),
                    (r'Razorpay\s*\(', 'Razorpay', 0.95),
                    (r'Klarna\.Payments', 'Klarna', 0.95),
                    (r'Chargebee\.init', 'Chargebee', 0.95),
                    (r'recurly\.configure', 'Recurly', 0.95),
                    (r'Paddle\.Setup', 'Paddle', 0.95),
                    (r'FlutterwaveCheckout', 'Flutterwave', 0.95),
                    (r'PaystackPop', 'Paystack', 0.95),
                    (r'MercadoPago', 'Mercado Pago', 0.90),
                    (r'Accept\.dispatchData', 'Authorize.Net', 0.95),
                    (r'Plaid\.create', 'Plaid', 0.95),
                    (r'ApplePaySession', 'Apple Pay', 0.95),
                    (r'google\.payments\.api', 'Google Pay', 0.90),
                ]
                
                for pattern, gateway, confidence in sdk_init_patterns:
                    if re.search(pattern, inline_content, re.IGNORECASE):
                        info.gateway_hint = gateway
                        info.confidence = confidence
                        scripts.append(info)
                        break
    
    return scripts


def _extract_forms(soup) -> List[FormInfo]:
    """Extract form elements and analyze for payment forms."""
    forms = []
    
    for form in soup.find_all('form'):
        action = form.get('action', '')
        method = form.get('method', 'GET').upper()
        form_id = form.get('id', '')
        class_names = form.get('class', [])
        if isinstance(class_names, str):
            class_names = class_names.split()
        
        info = FormInfo(
            action=action,
            method=method,
            id=form_id,
            class_names=class_names
        )
        
        # Check for card-related inputs within this form
        form_html = str(form)
        
        for pattern in CARD_NUMBER_PATTERNS:
            if re.search(pattern, form_html, re.IGNORECASE):
                info.has_card_fields = True
                break
        
        for pattern in EXPIRY_PATTERNS:
            if re.search(pattern, form_html, re.IGNORECASE):
                info.has_expiry_fields = True
                break
        
        for pattern in CVV_PATTERNS:
            if re.search(pattern, form_html, re.IGNORECASE):
                info.has_cvv_fields = True
                break
        
        # Check form action for payment gateway hints
        gateway_action_patterns = [
            (r'stripe\.com', 'Stripe'),
            (r'paypal\.com', 'PayPal'),
            (r'braintree', 'Braintree'),
            (r'authorize\.net', 'Authorize.Net'),
            (r'checkout\.com', 'Checkout.com'),
        ]
        
        for pattern, gateway in gateway_action_patterns:
            if re.search(pattern, action, re.IGNORECASE):
                info.gateway_hint = gateway
                break
        
        forms.append(info)
    
    return forms


def _extract_iframes(soup) -> List[IframeInfo]:
    """Extract iframe elements and analyze for payment embeds."""
    iframes = []
    
    for iframe in soup.find_all('iframe'):
        src = iframe.get('src', '')
        
        if not src:
            continue
        
        info = IframeInfo(
            src=src,
            id=iframe.get('id'),
            name=iframe.get('name')
        )
        
        # Check against known payment iframe patterns
        for gateway, patterns in IFRAME_SRC_PATTERNS.items():
            for pattern, confidence in patterns:
                if re.search(pattern, src, re.IGNORECASE):
                    info.gateway_hint = gateway
                    info.confidence = max(info.confidence, confidence)
                    break
            if info.gateway_hint:
                break
        
        iframes.append(info)
    
    return iframes


def _extract_meta_tags(soup) -> Dict[str, str]:
    """Extract meta tags that might indicate payment providers."""
    meta_info = {}
    
    # Payment-related meta tag names
    payment_meta_names = [
        'generator',
        'platform',
        'shopify',
        'woocommerce',
        'magento',
        'bigcommerce',
        'squarespace',
    ]
    
    for meta in soup.find_all('meta'):
        name = meta.get('name', '').lower()
        content = meta.get('content', '')
        
        if name and content:
            # Check if this is a payment-related meta tag
            for pm_name in payment_meta_names:
                if pm_name in name or pm_name in content.lower():
                    meta_info[name] = content
                    break
            
            # Also capture generator tags
            if name == 'generator':
                meta_info['generator'] = content
    
    # Check og:site_name for e-commerce platforms
    og_site = soup.find('meta', property='og:site_name')
    if og_site and og_site.get('content'):
        meta_info['og:site_name'] = og_site.get('content')
    
    return meta_info


def _extract_input_fields(soup) -> List[InputFieldInfo]:
    """Extract input fields and identify payment-related ones."""
    inputs = []
    
    for inp in soup.find_all(['input', 'select']):
        name = inp.get('name', '')
        inp_id = inp.get('id', '')
        inp_type = inp.get('type', 'text')
        autocomplete = inp.get('autocomplete', '')
        class_names = inp.get('class', [])
        if isinstance(class_names, str):
            class_names = class_names.split()
        
        # Extract data attributes
        data_attrs = {
            k: v for k, v in inp.attrs.items()
            if k.startswith('data-')
        }
        
        info = InputFieldInfo(
            name=name,
            id=inp_id,
            type=inp_type,
            autocomplete=autocomplete,
            class_names=class_names,
            data_attributes=data_attrs
        )
        
        # Determine field type based on attributes
        combined = f"{name} {inp_id} {autocomplete} {' '.join(class_names)}".lower()
        
        # Check for card number
        for pattern in CARD_NUMBER_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                info.field_type = 'card_number'
                break
        
        if not info.field_type:
            for pattern in EXPIRY_PATTERNS:
                if re.search(pattern, combined, re.IGNORECASE):
                    info.field_type = 'expiry'
                    break
        
        if not info.field_type:
            for pattern in CVV_PATTERNS:
                if re.search(pattern, combined, re.IGNORECASE):
                    info.field_type = 'cvv'
                    break
        
        # Check autocomplete values
        if not info.field_type:
            for field_type, ac_values in PAYMENT_AUTOCOMPLETE_VALUES.items():
                if autocomplete.lower() in ac_values:
                    info.field_type = field_type
                    break
        
        # Only include payment-related inputs
        if info.field_type or any('payment' in attr.lower() or 'card' in attr.lower() 
                                   for attr in data_attrs.keys()):
            inputs.append(info)
    
    return inputs


def _aggregate_gateway_detections(structure: HTMLStructure) -> Dict[str, float]:
    """Aggregate all gateway detections from parsed elements."""
    detections: Dict[str, float] = {}
    
    # From scripts
    for script in structure.scripts:
        if script.gateway_hint:
            existing = detections.get(script.gateway_hint, 0)
            detections[script.gateway_hint] = max(existing, script.confidence)
    
    # From iframes
    for iframe in structure.iframes:
        if iframe.gateway_hint:
            existing = detections.get(iframe.gateway_hint, 0)
            detections[iframe.gateway_hint] = max(existing, iframe.confidence)
    
    # From forms (lower confidence since just action URL)
    for form in structure.forms:
        if form.gateway_hint:
            existing = detections.get(form.gateway_hint, 0)
            detections[form.gateway_hint] = max(existing, 0.70)
    
    # From meta tags (e-commerce platforms that have payments)
    generator = structure.meta_tags.get('generator', '').lower()
    if 'shopify' in generator:
        detections['Shopify Payments'] = max(detections.get('Shopify Payments', 0), 0.60)
    if 'woocommerce' in generator:
        detections['WooCommerce'] = max(detections.get('WooCommerce', 0), 0.60)
    if 'magento' in generator:
        detections['Magento'] = max(detections.get('Magento', 0), 0.60)
    
    return detections


# =============================================================================
# HIGH-LEVEL ANALYSIS FUNCTIONS
# =============================================================================

def detect_gateways_from_html_structure(html: str) -> Dict[str, float]:
    """
    Detect payment gateways using structured HTML parsing.
    
    This provides a complementary detection method to regex-based detection,
    with higher confidence for SDK includes and embedded iframes.
    
    Args:
        html: Raw HTML content
        
    Returns:
        Dictionary of gateway_name -> confidence_score
    """
    structure = parse_html_structure(html)
    return structure.detected_gateways


def detect_inbuilt_payment_from_structure(html: str) -> tuple:
    """
    Detect inbuilt payment forms using structured HTML parsing.
    
    This is more accurate than regex-based detection because it understands
    the form structure and can identify card input fields in context.
    
    Args:
        html: Raw HTML content
        
    Returns:
        Tuple of (has_inbuilt: bool, components: dict)
    """
    structure = parse_html_structure(html)
    
    components = {
        'card_form': structure.has_card_inputs,
        'expiry': any(inp.field_type == 'expiry' for inp in structure.input_fields),
        'cvv_form': any(inp.field_type == 'cvv' for inp in structure.input_fields),
    }
    
    # Also check forms
    for form in structure.forms:
        if form.has_card_fields:
            components['card_form'] = True
        if form.has_expiry_fields:
            components['expiry'] = True
        if form.has_cvv_fields:
            components['cvv_form'] = True
    
    # Inbuilt if has card number and at least one other component
    has_inbuilt = components['card_form'] and (components['expiry'] or components['cvv_form'])
    
    return has_inbuilt, components


def get_payment_form_details(html: str) -> Dict:
    """
    Get detailed information about payment forms on the page.
    
    Returns:
        Dictionary with payment form analysis
    """
    structure = parse_html_structure(html)
    
    return {
        'has_payment_form': structure.has_payment_form,
        'has_card_inputs': structure.has_card_inputs,
        'payment_forms': [
            {
                'action': f.action,
                'method': f.method,
                'has_card': f.has_card_fields,
                'has_expiry': f.has_expiry_fields,
                'has_cvv': f.has_cvv_fields,
                'gateway_hint': f.gateway_hint,
            }
            for f in structure.forms
            if f.has_card_fields or f.has_expiry_fields or f.has_cvv_fields
        ],
        'payment_iframes': [
            {
                'src': i.src,
                'gateway': i.gateway_hint,
                'confidence': i.confidence,
            }
            for i in structure.iframes
            if i.gateway_hint
        ],
        'sdk_scripts': [
            {
                'src': s.src,
                'gateway': s.gateway_hint,
                'confidence': s.confidence,
            }
            for s in structure.scripts
            if s.gateway_hint
        ],
    }
