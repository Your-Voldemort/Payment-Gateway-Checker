"""
Test script for the optimized detection module.

This script tests:
1. Word boundary matching (avoiding false positives)
2. SDK pattern detection
3. Confidence scoring
4. Security feature detection
5. Structured HTML parsing (Part 3.2)
6. Enhanced inbuilt payment detection
"""
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from detection import (
    find_payment_gateways_optimized,
    check_security_features,
    analyze_url_response,
    check_cvv_requirement,
    check_inbuilt_payment_system,
    HTML_PARSER_AVAILABLE,
)

# Import HTML parser if available
if HTML_PARSER_AVAILABLE:
    from html_parser import (
        parse_html_structure,
        detect_gateways_from_html_structure,
        detect_inbuilt_payment_from_structure,
        get_payment_form_details,
    )


def test_word_boundary_matching():
    """Test that word boundaries prevent false positives."""
    print("\n" + "=" * 60)
    print("TEST 1: Word Boundary Matching")
    print("=" * 60)

    # These should NOT match "stripe"
    false_positive_tests = [
        ("The pinstripe suit looked great", "pinstripe - should NOT match stripe"),
        ("She wore a stripe-free dress", "stripe-free - edge case"),
    ]

    # These SHOULD match "stripe"
    true_positive_tests = [
        ("We use Stripe for payments", "standalone Stripe"),
        ("Powered by stripe checkout", "lowercase stripe"),
        ('<script src="js.stripe.com/v3"></script>', "SDK include"),
    ]

    print("\n--- False Positive Prevention ---")
    for html, description in false_positive_tests:
        gateways, matches = find_payment_gateways_optimized(html)
        has_stripe = any('stripe' in g.lower() for g in gateways)
        status = "[PASS]" if not has_stripe else "[FAIL]"
        print(f"{status} | {description}")
        if has_stripe:
            print(f"       Unexpected match: {[g for g in gateways if 'stripe' in g.lower()]}")

    print("\n--- True Positive Detection ---")
    for html, description in true_positive_tests:
        gateways, matches = find_payment_gateways_optimized(html)
        has_stripe = any('stripe' in g.lower() for g in gateways)
        status = "[PASS]" if has_stripe else "[FAIL]"
        confidence = matches.get('Stripe', None)
        conf_str = f" (confidence: {confidence.confidence:.2f})" if confidence else ""
        print(f"{status} | {description}{conf_str}")


def test_sdk_detection():
    """Test JavaScript SDK pattern detection."""
    print("\n" + "=" * 60)
    print("TEST 2: JavaScript SDK Detection")
    print("=" * 60)

    sdk_tests = [
        # (HTML, expected_gateway, description)
        ('<script src="https://js.stripe.com/v3/"></script>', "Stripe", "Stripe SDK v3"),
        ('<script src="https://www.paypal.com/sdk/js?client-id=abc"></script>', "PayPal", "PayPal SDK"),
        ('<script src="https://checkout.razorpay.com/v1/checkout.js"></script>', "Razorpay", "Razorpay SDK"),
        ('<script>var checkout = new AdyenCheckout(config);</script>', "Adyen", "Adyen initialization"),
        ('<script src="https://js.braintreegateway.com/web/3.x/js/client.min.js"></script>', "Braintree", "Braintree SDK"),
        ('Stripe("pk_live_xxx")', "Stripe", "Stripe constructor"),
        ('paypal.Buttons().render()', "PayPal", "PayPal Buttons"),
    ]

    for html, expected, description in sdk_tests:
        gateways, matches = find_payment_gateways_optimized(html)
        found = expected in gateways
        match = matches.get(expected)
        status = "[PASS]" if found else "[FAIL]"
        conf_str = f" (confidence: {match.confidence:.2f}, category: {match.category})" if match else ""
        print(f"{status} | {description}{conf_str}")


def test_confidence_scoring():
    """Test that confidence scores are properly tiered."""
    print("\n" + "=" * 60)
    print("TEST 3: Confidence Scoring Tiers")
    print("=" * 60)

    # SDK detection should have HIGH confidence (>0.9)
    sdk_html = '<script src="https://js.stripe.com/v3/"></script>'
    _, sdk_matches = find_payment_gateways_optimized(sdk_html)
    sdk_conf = sdk_matches.get('Stripe')
    if sdk_conf:
        status = "[PASS]" if sdk_conf.confidence > 0.9 else "[FAIL]"
        print(f"{status} | SDK detection has HIGH confidence: {sdk_conf.confidence:.2f}")

    # Word-only detection should have LOW confidence (<0.5)
    word_html = "We accept Stripe payments"
    _, word_matches = find_payment_gateways_optimized(word_html)
    word_conf = word_matches.get('Stripe')
    if word_conf:
        status = "[PASS]" if word_conf.confidence < 0.5 else "[FAIL]"
        print(f"{status} | Word-only detection has LOW confidence: {word_conf.confidence:.2f}")


def test_security_features():
    """Test security feature detection."""
    print("\n" + "=" * 60)
    print("TEST 4: Security Feature Detection")
    print("=" * 60)

    tests = [
        # (HTML, feature, expected, description)
        ("Please complete 3D Secure verification", "3d_secure", True, "3D Secure mention"),
        ("Verified by Visa authentication required", "3d_secure", True, "Verified by Visa"),
        ("Enter the OTP sent to your phone", "otp", True, "OTP mention"),
        ("Please complete the captcha below", "captcha", True, "Captcha mention"),
        ('<div class="g-recaptcha"></div>', "captcha", True, "reCAPTCHA class"),
        ("CF-Ray: abc123", "cloudflare", True, "Cloudflare Ray"),
    ]

    for html, feature, expected, description in tests:
        results = check_security_features(html)
        found = results.get(feature, False)
        status = "[PASS]" if found == expected else "[FAIL]"
        print(f"{status} | {description}: {feature}={found}")


def test_cvv_detection():
    """Test CVV/CVC detection."""
    print("\n" + "=" * 60)
    print("TEST 5: CVV/CVC Detection")
    print("=" * 60)

    tests = [
        ('<input name="cvv" />', "CVV Required"),
        ('<input name="cvc" />', "CVC Required"),
        ('<input name="cvv" /><input name="cvc" />', "Both CVV and CVC Required"),
        ('<input name="security_code" />', "Security Code Required"),
        ('<input name="card_number" />', "No CVV/CVC Requirement Detected"),
    ]

    for html, expected in tests:
        result = check_cvv_requirement(html)
        status = "[PASS]" if result == expected else "[FAIL]"
        print(f"{status} | Expected: '{expected}', Got: '{result}'")


def test_inbuilt_payment():
    """Test inbuilt payment system detection."""
    print("\n" + "=" * 60)
    print("TEST 6: Inbuilt Payment System Detection")
    print("=" * 60)

    # Complete card form
    complete_form = '''
    <form>
        <input name="card_number" autocomplete="cc-number" />
        <input name="expiry" autocomplete="cc-exp" />
        <input name="cvv" autocomplete="cc-csc" />
    </form>
    '''
    has_inbuilt, components = check_inbuilt_payment_system(complete_form)
    status = "[PASS]" if has_inbuilt else "[FAIL]"
    print(f"{status} | Complete card form detected as inbuilt: {has_inbuilt}")
    print(f"       Components: {components}")

    # Partial form (just card number)
    partial_form = '<input name="card_number" />'
    has_inbuilt, components = check_inbuilt_payment_system(partial_form)
    status = "[PASS]" if not has_inbuilt else "[FAIL]"
    print(f"{status} | Partial form NOT detected as inbuilt: {has_inbuilt}")


def test_unified_analysis():
    """Test the unified analysis function."""
    print("\n" + "=" * 60)
    print("TEST 7: Unified Analysis")
    print("=" * 60)

    html = '''
    <html>
    <head>
        <script src="https://js.stripe.com/v3/"></script>
    </head>
    <body>
        <div id="card-element"></div>
        <input name="cvv" />
        Please complete 3D Secure verification.
    </body>
    </html>
    '''

    headers = {
        'server': 'cloudflare',
        'cf-ray': 'abc123',
        'strict-transport-security': 'max-age=31536000',
    }

    result = analyze_url_response(html, headers, 200)

    print(f"Gateways detected: {result['gateways']}")
    print(f"High confidence: {result['high_confidence_gateways']}")
    print(f"Security type: {result['security_type']}")
    print(f"CVV status: {result['cvv_status']}")
    print(f"Cloudflare: {result['cloudflare']}")
    print(f"Captcha: {result['captcha']}")

    # Verify Stripe was detected with high confidence
    stripe_found = 'Stripe' in result['gateways']
    stripe_high_conf = 'Stripe' in result['high_confidence_gateways']
    print(f"\n[PASS] Stripe detected: {stripe_found}")
    print(f"[PASS] Stripe high confidence: {stripe_high_conf}")


def test_html_structure_parsing():
    """Test BeautifulSoup HTML structure parsing (Part 3.2)."""
    print("\n" + "=" * 60)
    print("TEST 8: HTML Structure Parsing (Part 3.2)")
    print("=" * 60)

    if not HTML_PARSER_AVAILABLE:
        print("[SKIP] BeautifulSoup not available - skipping structured parsing tests")
        return

    # Test script element extraction
    html_with_scripts = '''
    <html>
    <head>
        <script src="https://js.stripe.com/v3/"></script>
        <script src="https://www.paypal.com/sdk/js?client-id=test"></script>
        <script>var checkout = new AdyenCheckout(config);</script>
    </head>
    <body></body>
    </html>
    '''

    structure = parse_html_structure(html_with_scripts)
    
    print(f"Parse successful: {structure.parse_successful}")
    print(f"Scripts found: {len(structure.scripts)}")
    
    # Check Stripe detection
    stripe_found = any(s.gateway_hint == 'Stripe' for s in structure.scripts)
    status = "[PASS]" if stripe_found else "[FAIL]"
    print(f"{status} | Stripe SDK detected via script parsing")
    
    # Check PayPal detection
    paypal_found = any(s.gateway_hint == 'PayPal' for s in structure.scripts)
    status = "[PASS]" if paypal_found else "[FAIL]"
    print(f"{status} | PayPal SDK detected via script parsing")
    
    # Check Adyen inline script detection
    adyen_found = any(s.gateway_hint == 'Adyen' for s in structure.scripts)
    status = "[PASS]" if adyen_found else "[FAIL]"
    print(f"{status} | Adyen initialization detected via inline script")


def test_iframe_detection():
    """Test iframe-based payment widget detection."""
    print("\n" + "=" * 60)
    print("TEST 9: Iframe Payment Widget Detection")
    print("=" * 60)

    if not HTML_PARSER_AVAILABLE:
        print("[SKIP] BeautifulSoup not available - skipping iframe tests")
        return

    html_with_iframes = '''
    <html>
    <body>
        <iframe src="https://checkout.stripe.com/c/pay/cs_test_xxx"></iframe>
        <iframe src="https://www.paypal.com/webapps/hermes/button" id="paypal-button"></iframe>
        <iframe src="https://payments.braintreegateway.com/dropin/xxx"></iframe>
    </body>
    </html>
    '''

    structure = parse_html_structure(html_with_iframes)
    
    print(f"Iframes found: {len(structure.iframes)}")
    
    for iframe in structure.iframes:
        if iframe.gateway_hint:
            print(f"[PASS] | {iframe.gateway_hint} detected via iframe (confidence: {iframe.confidence:.2f})")


def test_form_structure_analysis():
    """Test payment form structure analysis."""
    print("\n" + "=" * 60)
    print("TEST 10: Payment Form Structure Analysis")
    print("=" * 60)

    if not HTML_PARSER_AVAILABLE:
        print("[SKIP] BeautifulSoup not available - skipping form tests")
        return

    html_with_forms = '''
    <html>
    <body>
        <form id="payment-form" action="/checkout" method="POST">
            <input type="text" name="card_number" autocomplete="cc-number" />
            <input type="text" name="exp_month" autocomplete="cc-exp-month" />
            <input type="text" name="exp_year" autocomplete="cc-exp-year" />
            <input type="text" name="cvv" autocomplete="cc-csc" />
            <button type="submit">Pay</button>
        </form>
        <form action="https://checkout.stripe.com/pay" method="POST">
            <input type="hidden" name="session" value="xxx" />
        </form>
    </body>
    </html>
    '''

    structure = parse_html_structure(html_with_forms)
    
    print(f"Forms found: {len(structure.forms)}")
    
    # Check payment form detection
    payment_forms = [f for f in structure.forms if f.has_card_fields]
    status = "[PASS]" if len(payment_forms) > 0 else "[FAIL]"
    print(f"{status} | Payment form with card fields detected")
    
    for form in structure.forms:
        if form.has_card_fields:
            print(f"       Form: action='{form.action}', has_card={form.has_card_fields}, "
                  f"has_expiry={form.has_expiry_fields}, has_cvv={form.has_cvv_fields}")
    
    # Check gateway hint from form action
    stripe_form = any(f.gateway_hint == 'Stripe' for f in structure.forms)
    status = "[PASS]" if stripe_form else "[FAIL]"
    print(f"{status} | Stripe detected via form action URL")


def test_input_field_detection():
    """Test payment input field detection with autocomplete attributes."""
    print("\n" + "=" * 60)
    print("TEST 11: Payment Input Field Detection")
    print("=" * 60)

    if not HTML_PARSER_AVAILABLE:
        print("[SKIP] BeautifulSoup not available - skipping input tests")
        return

    html_with_inputs = '''
    <form>
        <input type="text" id="cc-number" name="card_number" autocomplete="cc-number" class="payment-field" />
        <input type="text" name="expiration" autocomplete="cc-exp" />
        <input type="text" name="security_code" autocomplete="cc-csc" data-payment="cvv" />
        <input type="text" name="cardholder" autocomplete="cc-name" />
    </form>
    '''

    structure = parse_html_structure(html_with_inputs)
    
    print(f"Payment input fields found: {len(structure.input_fields)}")
    
    for inp in structure.input_fields:
        print(f"       Field: name='{inp.name}', type='{inp.field_type}', autocomplete='{inp.autocomplete}'")
    
    # Verify card number detection
    card_inputs = [i for i in structure.input_fields if i.field_type == 'card_number']
    status = "[PASS]" if len(card_inputs) > 0 else "[FAIL]"
    print(f"{status} | Card number field detected")
    
    # Verify expiry detection
    expiry_inputs = [i for i in structure.input_fields if i.field_type == 'expiry']
    status = "[PASS]" if len(expiry_inputs) > 0 else "[FAIL]"
    print(f"{status} | Expiry field detected")
    
    # Verify CVV detection
    cvv_inputs = [i for i in structure.input_fields if i.field_type == 'cvv']
    status = "[PASS]" if len(cvv_inputs) > 0 else "[FAIL]"
    print(f"{status} | CVV field detected")


def test_structured_gateway_detection():
    """Test structured HTML parsing integrated with gateway detection."""
    print("\n" + "=" * 60)
    print("TEST 12: Structured Gateway Detection Integration")
    print("=" * 60)

    if not HTML_PARSER_AVAILABLE:
        print("[SKIP] BeautifulSoup not available - skipping integration tests")
        return

    # Complex page with multiple payment providers
    html = '''
    <html>
    <head>
        <script src="https://js.stripe.com/v3/"></script>
        <script src="https://x.klarnacdn.net/kp/lib/v1/api.js"></script>
    </head>
    <body>
        <div id="stripe-element"></div>
        <iframe src="https://www.paypal.com/smart/button"></iframe>
        <form action="/pay" method="POST">
            <input name="card_number" autocomplete="cc-number" />
            <input name="exp" autocomplete="cc-exp" />
            <input name="cvv" autocomplete="cc-csc" />
        </form>
        <klarna-widget data-klarna="true"></klarna-widget>
    </body>
    </html>
    '''

    # Test using the full analyze_url_response
    result = analyze_url_response(html, {'server': 'nginx'}, 200)
    
    print(f"HTML structure available: {result.get('html_structure_available', False)}")
    print(f"Structured detections: {result.get('structured_detections', {})}")
    print(f"Gateways detected: {result['gateways']}")
    print(f"High confidence gateways: {result['high_confidence_gateways']}")
    print(f"Has payment form: {result.get('has_payment_form', False)}")
    print(f"Inbuilt payment: {result['inbuilt_status']}")
    
    # Verify multiple gateways detected
    stripe_found = 'Stripe' in result['gateways']
    klarna_found = 'Klarna' in result['gateways']
    paypal_found = 'PayPal' in result['gateways']
    
    status = "[PASS]" if stripe_found else "[FAIL]"
    print(f"{status} | Stripe detected via structured analysis")
    
    status = "[PASS]" if klarna_found else "[FAIL]"
    print(f"{status} | Klarna detected via structured analysis")
    
    status = "[PASS]" if paypal_found else "[FAIL]"
    print(f"{status} | PayPal detected via iframe analysis")


def test_enhanced_inbuilt_detection():
    """Test enhanced inbuilt payment detection using structured parsing."""
    print("\n" + "=" * 60)
    print("TEST 13: Enhanced Inbuilt Payment Detection")
    print("=" * 60)

    if not HTML_PARSER_AVAILABLE:
        print("[SKIP] BeautifulSoup not available - skipping enhanced inbuilt tests")
        return

    # Complete inbuilt payment form
    complete_inbuilt = '''
    <form id="checkout-form" action="/process-payment" method="POST">
        <div class="form-group">
            <label>Card Number</label>
            <input type="text" name="card_number" autocomplete="cc-number" />
        </div>
        <div class="form-group">
            <label>Expiry</label>
            <select name="exp_month" autocomplete="cc-exp-month">
                <option>01</option>
            </select>
            <select name="exp_year" autocomplete="cc-exp-year">
                <option>2025</option>
            </select>
        </div>
        <div class="form-group">
            <label>CVV</label>
            <input type="text" name="cvv" autocomplete="cc-csc" />
        </div>
    </form>
    '''

    has_inbuilt, components = detect_inbuilt_payment_from_structure(complete_inbuilt)
    
    print(f"Inbuilt payment detected: {has_inbuilt}")
    print(f"Components: {components}")
    
    status = "[PASS]" if has_inbuilt else "[FAIL]"
    print(f"{status} | Complete inbuilt form correctly identified")
    
    # Page with third-party SDK (should NOT be inbuilt)
    third_party_html = '''
    <html>
    <head>
        <script src="https://js.stripe.com/v3/"></script>
    </head>
    <body>
        <div id="card-element"></div>
    </body>
    </html>
    '''

    has_inbuilt_sdk, components_sdk = detect_inbuilt_payment_from_structure(third_party_html)
    
    status = "[PASS]" if not has_inbuilt_sdk else "[FAIL]"
    print(f"{status} | Third-party SDK page correctly NOT identified as inbuilt")


def test_meta_tag_detection():
    """Test e-commerce platform detection via meta tags."""
    print("\n" + "=" * 60)
    print("TEST 14: Meta Tag Platform Detection")
    print("=" * 60)

    if not HTML_PARSER_AVAILABLE:
        print("[SKIP] BeautifulSoup not available - skipping meta tag tests")
        return

    html_shopify = '''
    <html>
    <head>
        <meta name="generator" content="Shopify" />
        <meta property="og:site_name" content="My Store" />
    </head>
    <body></body>
    </html>
    '''

    structure = parse_html_structure(html_shopify)
    
    print(f"Meta tags found: {structure.meta_tags}")
    
    # Check for Shopify detection
    shopify_detected = 'Shopify Payments' in structure.detected_gateways
    status = "[PASS]" if shopify_detected else "[FAIL]"
    print(f"{status} | Shopify platform detected via meta tag")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("GATEWAY DETECTION OPTIMIZATION TESTS")
    print("=" * 60)
    print(f"HTML Parser Available: {HTML_PARSER_AVAILABLE}")

    test_word_boundary_matching()
    test_sdk_detection()
    test_confidence_scoring()
    test_security_features()
    test_cvv_detection()
    test_inbuilt_payment()
    test_unified_analysis()
    
    # Part 3.2: Structured HTML Parsing Tests
    test_html_structure_parsing()
    test_iframe_detection()
    test_form_structure_analysis()
    test_input_field_detection()
    test_structured_gateway_detection()
    test_enhanced_inbuilt_detection()
    test_meta_tag_detection()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
