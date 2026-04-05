with open('detection.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '    \"WooCommerce\": [\n        (r\\'woocommerce\\', 0.70),\n        (r\\'wc-payment\\', 0.85),\n    ],\n}'
replacement = '''    "WooCommerce": [
        (r'woocommerce', 0.70),
        (r'wc-payment', 0.85),
    ],
    # Sift Science
    "Sift Science": [
        (r'js\.siftscience\.com', 0.98),
        (r'Sift\.init\(\s*\{', 0.98),
        (r'Sift\.signupEvent', 0.95),
        (r'Sift\.transactionEvent', 0.95),
    ],
    # Bolt
    "Bolt": [
        (r'cdn\.bolt\.com/checkout', 0.98),
        (r'Bolt\.checkout\(', 0.98),
        (r'bolt-button', 0.90),
        (r'data-bolt-', 0.90),
    ],
}'''

if target in content:
    content = content.replace(target, replacement)
    with open('detection.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Updated detection.py successfully')
else:
    print('Target not found in detection.py')

