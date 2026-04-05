import os

file_path = 'detection.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_woocommerce = False
replaced = False

for line in lines:
    if line.strip() == '"WooCommerce": [':
        in_woocommerce = True
    
    if in_woocommerce and line.strip() == '},':
        # unexpected, maybe skip
        pass
        
    if in_woocommerce and line == '}\n':
        # Found the end of WooCommerce / SDK_PATTERNS
        in_woocommerce = False
        new_lines.append(line) # append the original line or... wait, we need to append BEFORE the '}'
        
        # Actually it's easier to just accumulate lines.
        
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

target = '    "WooCommerce": [\n        (r\'woocommerce\', 0.70),\n        (r\'wc-payment\', 0.85),\n    ],\n}'

replacement = """    "WooCommerce": [
        (r'woocommerce', 0.70),
        (r'wc-payment', 0.85),
    ],
    # Sift Science
    "Sift Science": [
        (r'js\.siftscience\.com', 0.98),
        (r'Sift\.init\(\{', 0.98),
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
}"""

if target in text:
    text = text.replace(target, replacement)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)
    print("Replaced with LF!")
elif target.replace('\\n', '\\r\\n') in text:
    text = text.replace(target.replace('\\n', '\\r\\n'), replacement)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)
    print("Replaced with CRLF!")
else:
    print("Target not found.")
