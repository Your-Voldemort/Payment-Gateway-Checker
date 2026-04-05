import re

with open('config.py', 'r', encoding='utf-8') as f:
    config_content = f.read()

config_content = config_content.replace(
    '    # Fiserv / First Data\n    \"fiserv\", \"firstdata\", \"first data\", \"payeezy\", \"clover\", \"clover.com\",\n]',
    '    # Fiserv / First Data\n    \"fiserv\", \"firstdata\", \"first data\", \"payeezy\", \"clover\", \"clover.com\",\n    # Fraud Detection & Risk Management\n    \"sift science\", \"sift.com\", \"siftscience\", \"sift-science\", \"js.siftscience.com\", \"Sift.init\", \"_sift\",\n    # Airwallex - Multi-currency Global Payments\n    \"airwallex\", \"airwallex.com\", \"api.airwallex.com\", \"airwallex-js\", \"Airwallex.init\", \"airwallex-checkout\",\n    # Stripe Treasury & Financial Operations\n    \"stripe treasury\", \"stripe-treasury\", \"treasury.stripe.com\", \"stripe financial\", \"treasury-js\",\n]'
)

config_content = config_content.replace(
    '    \"wyre\",\n    \"banxa\",\n    \"alchemy pay\",\n]',
    '    \"wyre\",\n    \"banxa\",\n    \"alchemy pay\",\n    # OKX Pay - Crypto Exchange Payments\n    \"okx pay\", \"okxpay\", \"pay.okx.com\", \"okx-checkout\", \"okx-pay-button\", \"okx.com/pay\",\n    # THORSwap - Decentralized Exchange\n    \"thorswap\", \"thorswap.finance\", \"thorchain pay\", \"thorswap-widget\", \"tc-swap\", \"thor-bridge\",\n    # LN Markets - Lightning Network Commerce\n    \"lnmarkets.com\", \"ln markets\", \"lnm-\", \"lightning markets\", \"lightning-checkout\", \"ln-pay\",\n]'
)

config_content = config_content.replace(
    '    \"bluevine\",\n    \"kabbage\",\n    \"ondeck\",\n]',
    '    \"bluevine\",\n    \"kabbage\",\n    \"ondeck\",\n    # Block (formerly Square Cash for Business)\n    \"block.xyz\", \"block-checkout\", \"block payments\", \"block-pay\", \"cdn.block.com/js\",\n]'
)

config_content = config_content.replace(
    '    \"trolley\",\n    \"wise business\", \"transferwise business\",\n    # White-label',
    '    \"trolley\",\n    # Wise Business - International B2B Transfers\n    \"wise business\", \"wise-business\", \"transferwise business\", \"wise-commerce\", \"business.wise.com\",\n    # White-label'
)

config_content = config_content.replace(
    '    \"gravity payments\",\n    \"payline data\",\n    \"payment depot\",\n]',
    '    \"gravity payments\",\n    \"payline data\",\n    \"payment depot\",\n    # Bolt - One-Click Checkout\n    \"bolt.com\", \"bolt checkout\", \"cdn.bolt.com/checkout\", \"Bolt.checkout\", \"bolt-js\", \"bolt-button\",\n    # Tripwire - Payment Orchestration\n    \"tripwire.io\", \"tripwire payments\", \"tripwire-js\", \"tripwire-checkout\", \"api.tripwire.io\",\n]'
)

with open('config.py', 'w', encoding='utf-8') as f:
    f.write(config_content)

print('Updated config.py successfully')
