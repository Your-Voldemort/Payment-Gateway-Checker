"""Configuration management for the Telegram Gateway Hunter Bot."""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Bot configuration from environment variables."""
    
    # Telegram Bot Settings
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    OWNER_USER_ID = int(os.getenv('OWNER_USER_ID', 0))
    
    # Contact Information
    CONTACT_USERNAME = os.getenv('CONTACT_USERNAME', 'volde_is_back')
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'UrlDebugger_bot')
    
    # Request Settings
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 10))
    MAX_URLS_PER_REQUEST = int(os.getenv('MAX_URLS_PER_REQUEST', 10))

    # Bulk Scanning (/bulk on a replied .txt file).
    # URLs are scanned in batches of BULK_BATCH_SIZE; results are appended to a
    # per-user output file the user can download as CSV / TXT / JSON.
    BULK_BATCH_SIZE = int(os.getenv('BULK_BATCH_SIZE', 10))
    # Hard ceiling on URLs processed from a single file (protects the bot from
    # multi-hour jobs). Set generously so typical large lists run in full.
    MAX_BULK_URLS = int(os.getenv('MAX_BULK_URLS', 5000))
    # Directory where per-user bulk result files are accumulated.
    BULK_RESULTS_DIR = os.getenv('BULK_RESULTS_DIR', 'bulk_results')

    # Deep Scan (Power-ups P1/P2): probe checkout/cart pages & first-party JS bundles.
    # Set DEEP_SCAN_ENABLED=false to keep the fast homepage-only path.
    DEEP_SCAN_ENABLED = os.getenv('DEEP_SCAN_ENABLED', 'true').lower() == 'true'

    # Anti-bot / proxy settings (all optional).
    # PROXY_URL: single proxy, e.g. http://user:pass@host:port (http/https/socks5).
    # PROXY_LIST: comma-separated proxies; one is chosen per request (rotation).
    PROXY_URL = os.getenv('PROXY_URL', '').strip()
    PROXY_LIST = [p.strip() for p in os.getenv('PROXY_LIST', '').split(',') if p.strip()]
    # Promote curl_cffi (browser TLS/JA3/HTTP2 impersonation) to the primary fetch for a
    # domain after it returns a block/challenge, instead of only as a 400 fallback.
    CURL_CFFI_ON_BLOCK = os.getenv('CURL_CFFI_ON_BLOCK', 'true').lower() == 'true'
    # Browser profile(s) curl_cffi impersonates; comma-separated -> randomly chosen.
    # 'chrome' auto-tracks the latest; pin/rotate e.g. 'chrome131,chrome124,safari_ios'.
    CURL_IMPERSONATE = os.getenv('CURL_IMPERSONATE', 'chrome')
    
    # Rate Limiting
    ENABLE_RATE_LIMITING = os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true'
    RATE_LIMIT_MESSAGES = int(os.getenv('RATE_LIMIT_MESSAGES', 20))
    RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', 60))
    
    # File Paths
    USER_IDS_FILE = os.getenv('USER_IDS_FILE', 'user_ids.txt')
    LOG_FILE = os.getenv('LOG_FILE', 'bot.log')
    
    # User Agent Settings
    USER_AGENT_ROTATION = os.getenv('USER_AGENT_ROTATION', 'true').lower() == 'true'
    USER_AGENT_TYPE = os.getenv('USER_AGENT_TYPE', 'all')  # all, desktop, mobile, chrome, firefox, etc.
    DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    # Subscription Settings
    BTC_ADDRESS = os.getenv('BTC_ADDRESS', 'bc1qw79l29y4yp2chmwmj3nw4my062a3aazjctx4q6')
    LTC_ADDRESS = os.getenv('LTC_ADDRESS', 'ltc1q8sfrqzsahn7a0gcx6h5304ljf08k4vqvq04sau')
    USDT_TRC20_ADDRESS = os.getenv('USDT_TRC20_ADDRESS', 'TJpx8Knpv6toy2QKqWdt64W2HxVt7q8gef')

    SUBSCRIPTION_PLANS = {
        "1d": {"name": "1 Day", "price": "$5"},
        "1m": {"name": "1 Month", "price": "$20"},
        "3m": {"name": "3 Months", "price": "$50"},
        "6m": {"name": "6 Months", "price": "$90"},
        "1y": {"name": "1 Year", "price": "$150"}
    }

    @classmethod
    def validate(cls):
        """Validate required configuration."""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables")
        if not cls.OWNER_USER_ID:
            raise ValueError("OWNER_USER_ID is not set in environment variables")
        return True

# =============================================================================
# PAYMENT GATEWAY DETECTION SYSTEM
# =============================================================================
# Organized by category for maintainability. Detection uses case-insensitive
# substring matching against HTML response text, including:
# - Brand names and company identifiers
# - JavaScript SDK/library references
# - API endpoint patterns
# - CSS class names and HTML identifiers
# - Form action URLs and iframe sources
# =============================================================================

# --- MAJOR GLOBAL PROCESSORS ---
GATEWAYS_GLOBAL_MAJOR = [
    # Stripe ecosystem
    "stripe", "stripe.com", "js.stripe.com", "stripe-js", "stripe.js", "stripe connect",
    "stripe elements", "stripe checkout", "stripepayments", "pk_live_", "pk_test_",
    # PayPal ecosystem
    "paypal", "paypal.com", "paypalobjects.com", "braintree", "braintree-api",
    "braintreepayments", "braintree-web", "venmo", "paypal-button", "paypal-checkout",
    # Adyen
    "adyen", "adyen.com", "adyencheckout", "adyen-checkout", "adyen marketpay",
    "adyen-cse", "adyen-web", "adyenjs",
    # Checkout.com
    "checkout.com", "frames.checkout.com", "cko-", "cko-card-number",
    # Worldpay / FIS
    "worldpay", "worldpay.com", "worldpay.js", "worldline", "fisglobal",
    # Square
    "square", "squareup.com", "squarecdn.com", "sq-payment-form", "square-payment",
    # Authorize.Net variants
    "authorize.net", "authorizenet", "authorize-net", "accept.js", "acceptcore",
    "anet-", "authnet-",
    # CyberSource (Visa)
    "cybersource", "cybersource.com", "flex-microform", "cybs-",
    # Global Payments / TSYS
    "global payments", "globalpayments", "globalpay", "tsys", "heartland",
    "heartlandpaymentsystems", "hps-", "portico",
    # Fiserv / First Data
    "fiserv", "firstdata", "first data", "payeezy", "clover", "clover.com",
    # Fraud Detection & Risk Management
    "sift science", "sift.com", "siftscience", "sift-science", "js.siftscience.com", "Sift.init", "_sift",
    # Airwallex - Multi-currency Global Payments
    "airwallex", "airwallex.com", "api.airwallex.com", "airwallex-js", "Airwallex.init", "airwallex-checkout",
    # Stripe Treasury & Financial Operations
    "stripe treasury", "stripe-treasury", "treasury.stripe.com", "stripe financial", "treasury-js",
    # AI & ML Service Payment Processors
    "scale ai pay", "scale.com/pay", "scale-payment",
    "together ai pay", "together-payment", "together.ai/pay",
    "openai billing", "openai-billing", "platform.openai.com/account",
    "anthropic billing", "claude-billing", "console.anthropic.com",
]

# --- EUROPEAN PROCESSORS ---
GATEWAYS_EUROPE = [
    # Mollie (Netherlands)
    "mollie", "mollie.com", "molliecdn", "mollie-components",
    # Klarna (Sweden) - BNPL
    "klarna", "klarna.com", "klarna-checkout", "klarna-payments", "klarnacdn",
    "klarna-widget", "klarna-osm", "klarna_payments",
    # Adyen (Netherlands) - already in global
    # Stripe (Ireland/US) - already in global
    # SagePay / Opayo (UK)
    "sagepay", "opayo", "sage pay", "opayo.co.uk",
    # Worldline (EU)
    "worldline", "ingenico", "ogone", "payvision",
    # Nexi (Italy)
    "nexi", "nexi.it", "nexipay", "cartasi",
    # Paylike (Denmark)
    "paylike", "paylike.io",
    # SecurionPay (Switzerland)
    "securionpay", "securionpay.com",
    # Trustly (Sweden) - Open Banking
    "trustly", "trustly.com", "trustly.net",
    # iDEAL (Netherlands)
    "ideal", "ideal-payment", "ideal.nl", "idealcheckout",
    # Sofort/Sofortüberweisung (Germany)
    "sofort", "sofortüberweisung", "sofort.com", "sofortbanking",
    # Giropay (Germany)
    "giropay", "giropay.de",
    # Bancontact (Belgium)
    "bancontact", "bancontact.com", "bcmc", "payconiq",
    # Przelewy24 / P24 (Poland)
    "przelewy24", "p24", "przelewy24.pl", "dotpay", "tpay",
    # Blik (Poland)
    "blik", "blik.com",
    # EPS (Austria)
    "eps-überweisung", "eps.or.at",
    # Multibanco (Portugal)
    "multibanco", "sibs",
    # PayU Europe
    "payu", "payu.com", "payu latam", "payu.pl", "payu.in",
    # Paysera (Lithuania)
    "paysera", "paysera.com",
    # Paysafe ecosystem
    "paysafe", "paysafecard", "skrill", "neteller", "paysafe.com",
    # Revolut Pay
    "revolut", "revolut.com", "revolut pay",
    # Viva Wallet (Greece)
    "vivawallet", "viva.com", "viva wallet",
    # Swedbank Pay (Nordics)
    "swedbank pay", "swedbankpay", "payex",
    # SEB (Baltics)
    "sebpay",
    # Europe - Additional Processors
    "fondy", "fondy.ua", "fondy-checkout",
    "edenred", "edenred.com", "edenred-pay",
    "bluesnap europe", "bluesnap-eu",
    "datatrans", "datatrans.ch", "datatrans-checkout",
    "qiwi expansion", "qiwi-eu", "qiwi-europe",
    "yandex kassa", "yandex-kassa", "kassa.yandex",
]

# --- ASIA-PACIFIC PROCESSORS ---
GATEWAYS_APAC = [
    # India
    "razorpay", "razorpay.com", "rzp-", "checkout.razorpay.com",
    "paytm", "paytm.com", "paytmpayments", "paytmcdn",
    "phonepe", "phonepe.com",
    "juspay", "juspay.in",
    "cashfree", "cashfree.com",
    "payu india", "payubiz",
    "ccavenue", "ccavenue.com",
    "instamojo", "instamojo.com",
    "billdesk", "billdesk.com",
    "upi", "bhim", "upi://", "@upi", "upipay",
    "mobikwik", "freecharge", "airtel money india",
    # China
    "alipay", "alipay.com", "alipayobjects", "alipayplus",
    "wechat pay", "wechatpay", "wxpay", "tenpay", "weixin.qq.com",
    "unionpay", "unionpayintl", "chinapay",
    "jdpay", "jd.com/pay",
    # Japan
    "paypay", "paypay.ne.jp",
    "line pay", "linepay", "pay.line.me",
    "rakuten pay", "rakuten.co.jp",
    "konbini", "lawson", "familymart", "7-eleven pay", "ministop",
    "merpay", "mercari",
    "d払い", "d-payment", "docomo",
    "au pay", "aupay",
    "paidy", "paidy.com",
    "gmo payment", "gmo-pg", "gmopg",
    "softbank payment",
    "veritrans", "veritrans.co.jp",
    # South Korea
    "naver pay", "naverpay", "pay.naver.com",
    "kakao pay", "kakaopay", "pg.kakao.com",
    "toss", "tosspayments", "toss.im",
    "samsung pay", "samsungpay",
    "lg u+", "payco",
    "inicis", "kg inicis",
    "nicepay korea", "nicepayments",
    # Southeast Asia
    "grabpay", "grab pay", "grab.com",
    "gcash", "gcash.com",
    "paymaya", "maya.ph",
    "touch n go", "touchngo", "tngdigital",
    "shopee pay", "shopeepay", "shopee.com",
    "lazada wallet",
    "ovo", "ovo.id",
    "dana", "dana.id",
    "gopay", "gojek",
    "momo vietnam", "momo.vn",
    "zalopay", "zalo pay",
    "vnpay", "vnpay.vn",
    "payoo",
    "dragonpay", "dragonpay.ph",
    "2c2p", "2c2p.com",
    "omise", "omise.co",
    "xendit", "xendit.co",
    "ipay88", "ipay88.com",
    "billplz",
    "senangpay",
    "razer pay", "razerpay", "mol",
    # Australia/New Zealand
    "afterpay", "afterpay.com", "clearpay",
    "zip pay", "zippay", "zip.co", "quadpay",
    "humm", "humm-group", "bundll",
    "laybuy",
    "bpay", "bpay.com.au",
    "poli", "poli payments", "polipayments",
    "eway", "eway.com.au",
    "payway australia",
    "anz egate",
    "securepay australia",
    "fatzebra", "fat zebra",
    "pin payments", "pinpayments",
    "tyro", "tyro.com",
    # India - Additional Payment Solutions
    "phonepe switch", "bharat qr", "bharat-qr",
    "yono sbi pay", "yonosbi", "sbi.yono", "sbi-checkout",
    "icici imobile pay", "imobilepay", "imobile-checkout",
    "google pay india", "gpay.in",
    "amazon pay india", "amazonpay.in",
    "hdfc smartbuy", "smartbuy.hdfc",
    # Southeast Asia - Additional Platforms
    "linkaja", "link aja", "linkaja.id", "link-aja-pay",
    "seamoney", "sea money", "seamoney.com",
    "true money", "truemoney", "truemoney.com", "truemoney-wallet",
    "airasia pay", "airasia.com/pay", "airasia-checkout",
    "boost malaysia", "boost-pay", "boost.com.my",
    "dash", "dash.ubipay", "ubipay",
    "instapay philippines", "instapay.ph", "instapay-checkout",
]

# --- MIDDLE EAST & AFRICA ---
GATEWAYS_MEA = [
    # Middle East
    "fawry", "fawry.com", "myfawry",
    "telr", "telr.com",
    "paytabs", "paytabs.com",
    "payfort", "amazon payment services", "aps.amazon.ae",
    "hyperpay", "hyperpay.com",
    "tap payments", "tap.company", "tappayments",
    "moyasar", "moyasar.com",
    "paylink.sa",
    "checkout.com mena",
    "network international",
    "paymob", "paymob.com",
    "thawani",
    "tamara", "tamara.co", "tabby", "tabby.ai",
    "postpay",
    "spotii",
    "cashew payments",
    # Africa - Pan-African
    "flutterwave", "flutterwave.com", "flw-", "rave.flutterwave",
    "paystack", "paystack.com", "paystack.co", "js.paystack.co",
    "interswitch", "interswitch.com", "webpay.interswitchng",
    "dusupay", "dusupay.com",
    "yoco", "yoco.co.za",
    "peach payments",
    "paygate south africa", "paygate.co.za",
    "ozow", "i-pay", "ipay africa",
    "pawapay",
    "chipper cash", "chippercash",
    "cellulant",
    "korapay",
    # Mobile Money
    "m-pesa", "mpesa", "safaricom",
    "mtn mobile money", "mtn momo", "momo.mtn",
    "airtel money", "airtelmoney",
    "orange money", "orangemoney",
    "tigo pesa", "tigopesa",
    "vodacom", "vodafone cash",
    "ecocash",
    "equitel",
    # Africa - Additional Processors & Solutions
    "remitly", "remitly.com", "remitly-checkout",
    "worldremit", "world remit", "worldremit.com",
    "paga", "paga.com", "pagapay", "paga-checkout",
    "moov africa", "moov-pay", "moov.com",
    "indicina", "indicina.com",
    "okra.ai", "okra payments",
    "fintech express", "ftxpress",
    # Middle East - Additional Solutions
    "hala", "hala.pay", "halapay",
    "ziina", "ziina.com", "ziina-checkout",
    "myfatoorah", "myfatoorah.com", "fatoorah-checkout",
    "inswitch", "inswitch.me", "inswitch-payments",
    "apptap", "app-tap-payments",
    "gateway360", "360pay",
]

# --- LATIN AMERICA ---
GATEWAYS_LATAM = [
    # Mercado Pago (Argentina/LatAm)
    "mercado pago", "mercadopago", "mercadolibre",
    # PagSeguro / PagBank (Brazil)
    "pagseguro", "pagseguro.com.br", "pagbank",
    # EBANX (Brazil-focused)
    "ebanx", "ebanx.com", "ebanxpay",
    # dLocal (Uruguay)
    "dlocal", "dlocal.com",
    # OpenPay (Mexico)
    "openpay", "openpay.mx",
    # Conekta (Mexico)
    "conekta", "conekta.io", "conekta.com",
    # PayU Latin America
    "payu latam", "payulatam",
    # OXXO (Mexico cash)
    "oxxo", "oxxopay",
    # Boleto (Brazil)
    "boleto", "boleto bancário", "boletobancario",
    # PIX (Brazil)
    "pix", "pix.bcb", "bcb.gov.br/pix", "pixpay",
    # Nubank
    "nubank", "nupay",
    # PicPay
    "picpay", "picpay.com",
    # Cielo (Brazil)
    "cielo", "cielo.com.br",
    # Rede (Brazil)
    "userede", "rede.com.br",
    # GetNet (Brazil)
    "getnet", "getnet.com.br",
    # SafetyPay
    "safetypay",
    # Todito Cash
    "toditocash", "todito",
    # Kushki (Ecuador)
    "kushki", "kushkipagos",
    # Transbank (Chile)
    "transbank", "webpay", "webpay.cl",
    # Khipu (Chile)
    "khipu",
    # Nequi (Colombia)
    "nequi",
    # Daviplata (Colombia)
    "daviplata",
    # PSE (Colombia)
    "pse", "pagos seguros en línea",
    # Yape (Peru)
    "yape", "yape.com.pe",
    # Plin (Peru)
    "plin",
    # Culqi (Peru)
    "culqi", "culqi.com",
    # Flow (Chile)
    "flow.cl", "flowpayments",
    # Latin America - Additional Platforms
    "mulpago", "mulpago.com", "mulpago-checkout",
    "stoneco", "stone.com.br", "stone-checkout",
    "ifthenpay", "ifthenpay.com",
    "kuna payments", "kuna.io",
    "tuum", "tuum.io", "tuum-payments",
    "uala", "uala.com.ar", "uala-pay",
]

# --- CRYPTOCURRENCY PAYMENT PROCESSORS ---
GATEWAYS_CRYPTO = [
    # Major crypto processors
    "bitpay", "bitpay.com", "bp_hosted", "bitpay-hosted",
    "coinbase commerce", "commerce.coinbase.com", "coinbase-commerce",
    "coingate", "coingate.com",
    "nowpayments", "nowpayments.io", "now-payments",
    "btcpay", "btcpay server", "btcpayserver",
    "opennode", "opennode.com",
    "blockonomics", "blockonomics.co",
    "coinpayments", "coinpayments.net",
    "cryptomus",
    "plisio",
    "triple-a", "triple-a.io",
    "paybear",
    "globee",
    "coindirect",
    "utrust", "utrust.com",
    "coinspaid",
    "spectrocoin",
    "bitaps",
    "blockchain.com/pay",
    "binance pay", "binancepay",
    "crypto.com pay",
    "paywithterra",
    "moonpay", "moonpay.com",
    "transak",
    "ramp network",
    "simplex",
    "wyre",
    "banxa",
    "alchemy pay",
    # OKX Pay - Crypto Exchange Payments
    "okx pay", "okxpay", "pay.okx.com", "okx-checkout", "okx-pay-button", "okx.com/pay",
    # THORSwap - Decentralized Exchange
    "thorswap", "thorswap.finance", "thorchain pay", "thorswap-widget", "tc-swap", "thor-bridge",
    # LN Markets - Lightning Network Commerce
    "lnmarkets.com", "ln markets", "lnm-", "lightning markets", "lightning-checkout", "ln-pay",
    # Privacy & Monero Integration
    "monero integration", "monero pay", "moneroj", "monero-checkout",
    "zcash payments", "zcash-pay", "z.cash",
    "haveno", "haveno-network", "haveno-pay",
]

# --- BUY NOW PAY LATER (BNPL) ---
GATEWAYS_BNPL = [
    # Major BNPL
    "klarna",  # also in Europe
    "afterpay", "clearpay",
    "affirm", "affirm.com", "affirm-js",
    "sezzle", "sezzle.com", "sezzle-widget",
    "zip", "zip pay", "zip.co", "quadpay",
    # Regional BNPL
    "laybuy",
    "humm",
    "openpay bnpl",
    "splitit", "splitit.com",
    "perpay",
    "paybright", "affirm.ca",
    "scalapay", "scalapay.com",
    "alma", "getalma.eu",
    "oney",
    "pledg",
    "younited pay", "younitedpay",
    "billie", "billie.io",
    "riverty", "arvato",
    # Middle East BNPL
    "tamara", "tabby", "spotii", "postpay", "cashew",
    # Shopify installments
    "shop pay installments",
    # Paypal BNPL
    "pay in 4", "pay later paypal",
]

# --- B2B AND INVOICING PLATFORMS ---
GATEWAYS_B2B = [
    # B2B Payments
    "bill.com", "billcom",
    "tipalti", "tipalti.com",
    "plastiq",
    "melio", "meliopayments",
    "divvy", "getdivvy",
    "ramp", "ramp.com",
    "brex", "brex.com",
    "coupa pay",
    "airbase",
    "center",
    "rippling",
    "paymode-x",
    "comdata",
    "wex",
    # Invoicing with payments
    "stripe invoicing", "stripe billing",
    "freshbooks", "freshbooks.com",
    "xero", "xero.com",
    "quickbooks payments", "intuit payments",
    "wave", "waveapps",
    "zoho invoice", "zoho payments",
    "invoice ninja",
    "square invoices",
    "paypal invoicing",
    "harvest", "getharvest.com",
    # AR Automation
    "versapay",
    "plooto",
    "routable",
    "paystand",
    "fundbox",
    "bluevine",
    "kabbage",
    "ondeck",
    # Block (formerly Square Cash for Business)
    "block.xyz", "block-checkout", "block payments", "block-pay", "cdn.block.com/js",
    # SaaS Billing & Invoicing Updates
    "chargify enterprise", "chargify-ent",
    "zuora enterprise", "zuora-ent", "zuora-rev-rec",
    "sage intacct", "sage-intacct", "intacct.com",
    "infor cloudsuite", "infor-payments",
    "oracle payments", "oracle-netsuite-payments",
    "sap concur", "concur payments", "concur-pay",
]

# --- DIGITAL WALLETS ---
GATEWAYS_WALLETS = [
    # Global
    "apple pay", "applepay", "apple.com/apple-pay", "pk.eyJ",
    "google pay", "googlepay", "pay.google.com", "gpay",
    "samsung pay", "samsungpay",
    "amazon pay", "amazonpay", "payments.amazon",
    "paypal", "paypal.com",
    "venmo",
    # Regional
    "paytm wallet",
    "phonepe",
    "mobikwik",
    "freecharge",
    "alipay",
    "wechat pay",
    "line pay",
    "kakao pay",
    "grab pay",
    "shopee pay",
    "ovo",
    "gopay",
    "dana",
    "gcash",
    # E-money
    "webmoney", "wmtransfer",
    "payeer", "payeer.com",
    "qiwi", "qiwi.com",
    "yoomoney", "yandex money",
    "paysafecard",
    "neosurf",
    "astropay", "astropaycard",
    "ecovoucher",
    "cashlib",
]

# --- SUBSCRIPTION & RECURRING BILLING ---
GATEWAYS_SUBSCRIPTION = [
    "recurly", "recurly.com", "js.recurly.com",
    "chargebee", "chargebee.com", "cbjs",
    "paddle", "paddle.com", "paddle.js", "paddle-js",
    "fastspring", "fastspring.com",
    "zuora", "zuora.com",
    "chargify",
    "pabbly",
    "moonclerk",
    "memberful",
    "substack", "substack.com",
    "gumroad", "gumroad.com",
    "sellfy",
    "podia",
    "teachable payments",
    "kajabi payments",
    "thinkific payments",
    "circle.so",
    "buy me a coffee", "buymeacoffee",
    "ko-fi", "ko-fi.com",
    "patreon", "patreon.com",
    "open collective",
    "github sponsors",
    "lemonsqueezy", "lemon squeezy",
    # Wellness, Fitness & Membership Billing
    "mindbody pay", "mindbody payments", "mindbody-checkout",
    "zen planner", "zenplanner-pay", "zenplanner.com",
    "classpass payments", "classpass-checkout", "classpass.com",
    "virtuagym", "virtuagym-payments",
]

# --- OPEN BANKING & ACCOUNT-TO-ACCOUNT ---
GATEWAYS_OPEN_BANKING = [
    # Open Banking initiators
    "trustly",
    "plaid", "plaid.com", "link.plaid.com",
    "truelayer", "truelayer.com",
    "tink", "tink.com",
    "yodlee",
    "finicity",
    "mx",
    "yapily",
    "salt edge",
    "token.io",
    "volt", "volt.io",
    "gocardless instant bank pay",
    "ecospend",
    "vyne",
    "crezco",
    # ACH/Direct Debit
    "gocardless", "gc.js", "gocardless.com",
    "dwolla", "dwolla.com",
    "plaid ach",
    "stripe ach",
    "ach direct", "ach-debit",
    "sepa direct debit", "sepa-dd",
    "bacs direct debit",
]

# --- PAYMENT FACILITATION & WHITE-LABEL ---
GATEWAYS_PAYFAC = [
    # Payment Facilitators
    "stripe connect",
    "paypal commerce platform",
    "adyen for platforms", "adyen marketpay",
    "wepay", "wepay.com",
    "finix",
    "payoneer", "payoneer.com",
    "payouts.com",
    "hyperwallet",
    "trolley",
    # Wise Business - International B2B Transfers
    "wise business", "wise-business", "transferwise business", "wise-commerce", "business.wise.com",
    # White-label
    "checkout.com", "cko-",
    "payroc",
    "nuvei", "nuvei.com",
    "shift4", "shift4payments",
    "paysafe", "paysafe.com",
    "rapyd", "rapyd.net",
    "payrix",
    "stax", "staxpayments",
    "helcim",
    "dharma merchant",
    "fattmerchant",
    "gravity payments",
    "payline data",
    "payment depot",
    # Bolt - One-Click Checkout
    "bolt.com", "bolt checkout", "cdn.bolt.com/checkout", "Bolt.checkout", "bolt-js", "bolt-button",
    # Tripwire - Payment Orchestration
    "tripwire.io", "tripwire payments", "tripwire-js", "tripwire-checkout", "api.tripwire.io",
    # Embedded Finance Platforms
    "stripe embedded payments", "stripe-embedded", "embedded-payments-stripe",
    "checkout unified payments", "checkout-unified", "checkout-embedded",
    "dwolla embedded", "dwolla-embedded", "dwolla-api",
    "plaid payment initiation", "plaid-payments", "plaid-embedded",
    "finix embedded", "finix-checkout",
    "marqeta", "marqeta.com", "marqeta-api",
]

# --- E-COMMERCE PLATFORMS WITH PAYMENTS ---
GATEWAYS_ECOMMERCE = [
    # Shopify
    "shopify payments", "shop pay", "shopify.com/payments", "shopify-payment",
    "shopify checkout",
    # WooCommerce
    "woocommerce", "woo.com", "woocommerce-gateway", "wc-", "woocommerce-payments",
    # BigCommerce
    "bigcommerce", "bigcommerce.com",
    # Magento/Adobe Commerce
    "magento", "braintree magento", "magento-payments",
    # Squarespace
    "squarespace commerce", "squarespace.com",
    # Wix
    "wix payments", "wix.com/payments",
    # Ecwid
    "ecwid", "ecwid.com",
    # PrestaShop
    "prestashop",
    # OpenCart
    "opencart",
    # Volusion
    "volusion",
    # 3dcart/Shift4Shop
    "3dcart", "shift4shop",
    # Salesforce Commerce
    "salesforce commerce", "demandware",
]

# --- SDK/LIBRARY DETECTION SIGNATURES ---
# These are JavaScript includes, iframe sources, and API references
GATEWAY_SIGNATURES = [
    # Stripe
    "js.stripe.com/v3", "stripe.com/v3", "stripe-card-element", "StripeCheckout",
    # PayPal
    "paypal.com/sdk/js", "paypalobjects.com", "paypal-buttons", "paypal-button-v2",
    # Braintree
    "js.braintreegateway.com", "braintree-web", "braintree.client",
    # Adyen
    "checkoutshopper-live.adyen.com", "adyen.com/checkoutshopper", "AdyenCheckout",
    # Square
    "js.squareup.com/v2", "squarecdn.com/js/sq-", "SqPaymentForm",
    # Authorize.Net
    "jstest.authorize.net", "js.authorize.net", "Accept.dispatchData",
    # Klarna
    "klarna.com/checkout/v3", "x.klarnacdn.net", "Klarna.Payments",
    # Affirm
    "cdn1.affirm.com", "affirm.js", "AffirmUI",
    # Afterpay
    "static.afterpay.com", "afterpay.js", "afterpayjs",
    # Razorpay
    "checkout.razorpay.com/v1", "Razorpay", "razorpay.js",
    # Paytm
    "securegw.paytm.in", "merchantpgpui.paytm.in",
    # Mollie
    "js.mollie.com", "mollie.Components",
    # Google Pay
    "pay.google.com/gp/p/js/pay.js", "google.payments", "GooglePayButton",
    # Apple Pay
    "apple-pay-button", "ApplePaySession",
    # Checkout.com
    "cdn.checkout.com/js", "Frames.init",
    # Recurly
    "js.recurly.com/v4", "recurly.configure",
    # Chargebee
    "js.chargebee.com", "Chargebee.init",
    # 2Checkout/Verifone
    "2checkout.com", "verifone.cloud",
]

# --- GAMING & ENTERTAINMENT PAYMENT PROCESSORS ---
GATEWAYS_GAMING = [
    "xsolla", "xsolla.com", "xsolla-checkout", "xsolla-js",
    "tencent pay", "tencent payments", "tenpay", "tencent-pay",
    "vpay", "vpay.com", "v-pay",
    "unity monetization", "unity-pay", "monetization.unity.com",
    "unreal payments", "unreal monetization",
]

# --- COMBINE ALL GATEWAYS ---
PAYMENT_GATEWAYS = (
    GATEWAYS_GLOBAL_MAJOR +
    GATEWAYS_EUROPE +
    GATEWAYS_APAC +
    GATEWAYS_MEA +
    GATEWAYS_LATAM +
    GATEWAYS_CRYPTO +
    GATEWAYS_BNPL +
    GATEWAYS_B2B +
    GATEWAYS_WALLETS +
    GATEWAYS_SUBSCRIPTION +
    GATEWAYS_OPEN_BANKING +
    GATEWAYS_PAYFAC +
    GATEWAYS_ECOMMERCE +
    GATEWAYS_GAMING +
    GATEWAY_SIGNATURES
)

# Remove duplicates while preserving order
PAYMENT_GATEWAYS = list(dict.fromkeys(PAYMENT_GATEWAYS))

# Security check keywords
CAPTCHA_KEYWORDS = ['captcha', 'robot', 'verification', 'prove you are not a robot', 'challenge']

CLOUDFLARE_INDICATORS = ['please wait', 'checking your browser', 'cf-ray', 'cf-request-id', 'cloudflare']

SECURE_3D_KEYWORDS = [
    '3dsecure', '3d secure', 'secure3d', 'secure checkout', 'verified by visa',
    'mastercard securecode', 'secure verification', '3d-authentication', '3d-auth'
]

OTP_KEYWORDS = [
    'otp', 'one-time password', 'verification code', 'enter the code',
    'authentication code', 'sms code', 'mobile verification'
]

INBUILT_PAYMENT_KEYWORDS = [
    'native payment', 'integrated payment', 'built-in checkout',
    'secure payment on this site', 'on-site payment',
    'internal payment gateway'
]

# =============================================================================
# E-COMMERCE PLATFORM DETECTION
# =============================================================================
# Patterns to identify popular e-commerce platforms used by websites.
# Each platform has HTML/JS patterns and HTTP headers for detection.
# =============================================================================

ECOMMERCE_PLATFORMS = {
    "Shopify": {
        "patterns": [
            r"cdn\.shopify\.com", r"myshopify\.com", r"Shopify\.theme",
            r"shopify-section", r"shopify\.com/s/files",
            r"window\.Shopify", r"Shopify\.shop", r"shopify-buy",
            r"shopify-payment-button", r"shopifycdn\.com"
        ],
        "headers": ["x-shopify-stage", "x-shopid", "x-shopify-request-id"],
        "confidence": 0.95
    },
    "WooCommerce": {
        "patterns": [
            r"woocommerce", r"wc-block", r"wc-add-to-cart",
            r"wp-content/plugins/woocommerce", r"wc_add_to_cart_params",
            r"woocommerce-product", r"wc-cart-fragments", r"woocommerce-page",
            r"woocommerce\.css", r"woocommerce\.js"
        ],
        "headers": [],
        "confidence": 0.90
    },
    "Magento": {
        "patterns": [
            r"Magento", r"mage/", r"requirejs/require",
            r"static/version", r"skin/frontend", r"Mage\.Cookies",
            r"varien/", r"magento2", r"magento\.com",
            r"mage-error", r"magento_root"
        ],
        "headers": ["x-magento-", "x-magento-cache"],
        "confidence": 0.90
    },
    "BigCommerce": {
        "patterns": [
            r"bigcommerce\.com", r"cdn\.bcapp", r"stencil-utils",
            r"data-product-id", r"BCData", r"bigcommerce-logo",
            r"bigcommerce\.net", r"bc-sf-filter"
        ],
        "headers": ["x-bc-", "x-bc-store-hash"],
        "confidence": 0.90
    },
    "PrestaShop": {
        "patterns": [
            r"prestashop", r"presta", r"modules/ps_",
            r"js/jquery/plugins/", r"PrestaShop", r"prestashop\.com",
            r"ps-shoppingcart", r"prestashop-version"
        ],
        "headers": [],
        "confidence": 0.85
    },
    "OpenCart": {
        "patterns": [
            r"catalog/view/javascript", r"route=product",
            r"index\.php\?route=", r"opencart", r"opencart\.com",
            r"product_id=", r"catalog/view/theme"
        ],
        "headers": [],
        "confidence": 0.85
    },
    "Squarespace": {
        "patterns": [
            r"squarespace\.com", r"static\.squarespace",
            r"sqsp-", r"sqs-block", r"squarespace-cdn",
            r"sqs-system", r"squarespace\.net"
        ],
        "headers": ["x-servedby: squarespace", "x-contextid"],
        "confidence": 0.95
    },
    "Wix": {
        "patterns": [
            r"wix\.com", r"wixstatic\.com", r"_wix_browser_sess",
            r"wix-code-sdk", r"wixWindow", r"wix-ui",
            r"parastorage\.com", r"wixapps\.net"
        ],
        "headers": ["x-wix-", "x-wix-request-id"],
        "confidence": 0.95
    },
    "WordPress": {
        "patterns": [
            r"wp-content", r"wp-includes", r"wordpress",
            r"wp-json", r"wp-admin", r"wp-login",
            r"wp_", r"_wpnonce"
        ],
        "headers": ["x-powered-by: wordpress"],
        "confidence": 0.85
    },
    "Salesforce Commerce Cloud": {
        "patterns": [
            r"demandware", r"salesforce commerce cloud",
            r"dwanalytics", r"dw\.ac", r"dwre",
            r"demandware\.edgesuite\.net", r"dw-session"
        ],
        "headers": ["x-dw-request-id"],
        "confidence": 0.90
    },
    "Ecwid": {
        "patterns": [
            r"ecwid", r"ecwid\.com", r"ecwid-store",
            r"ec-store", r"ecwid-script", r"ecwidstores"
        ],
        "headers": [],
        "confidence": 0.90
    },
    "Webflow": {
        "patterns": [
            r"webflow", r"webflow\.com", r"webflow\.io",
            r"w-webflow", r"wf-page", r"webflowcdn"
        ],
        "headers": ["x-wf-"],
        "confidence": 0.90
    },
    "Volusion": {
        "patterns": [
            r"volusion", r"volusion\.com", r"vspfiles",
            r"volusion-", r"volution"
        ],
        "headers": [],
        "confidence": 0.85
    },
    "Shift4Shop": {
        "patterns": [
            r"3dcart", r"shift4shop", r"3dcartstores",
            r"shift4shop\.com"
        ],
        "headers": [],
        "confidence": 0.85
    }
}

# Cart Abandonment and Recovery Tools Detection
CART_ABANDONMENT_TOOLS = {
    "Klaviyo": {
        "patterns": [
            r"klaviyo\.com", r"static\.klaviyo\.com", r"_learnq",
            r"klaviyo-form", r"kl_", r"klaviyo\.push"
        ],
        "type": "email_marketing",
        "confidence": 0.90
    },
    "CartHook": {
        "patterns": [
            r"carthook\.com", r"carthook", r"ch_",
            r"carthook-checkout"
        ],
        "type": "post_purchase",
        "confidence": 0.85
    },
    "Privy": {
        "patterns": [
            r"privy\.com", r"widget\.privy\.com", r"privy-popup",
            r"privy-widget", r"_privy_"
        ],
        "type": "popup_conversion",
        "confidence": 0.85
    },
    "OptinMonster": {
        "patterns": [
            r"optinmonster\.com", r"optmnstr", r"om-",
            r"omapi", r"optinmonster"
        ],
        "type": "lead_capture",
        "confidence": 0.85
    },
    "Drip": {
        "patterns": [
            r"getdrip\.com", r"dc\.js", r"_dcq",
            r"drip\.com", r"drip-widget"
        ],
        "type": "email_automation",
        "confidence": 0.85
    },
    "Rejoiner": {
        "patterns": [
            r"rejoiner\.com", r"rj\.js", r"rejoiner",
            r"rj-track"
        ],
        "type": "cart_recovery",
        "confidence": 0.85
    },
    "Jilt": {
        "patterns": [
            r"jilt\.com", r"jilt", r"jilt-widget",
            r"jiltcdn"
        ],
        "type": "cart_recovery",
        "confidence": 0.80
    },
    "Barilliance": {
        "patterns": [
            r"barilliance\.com", r"barilliance", r"brcdn",
            r"brl-cdn"
        ],
        "type": "personalization",
        "confidence": 0.80
    },
    "SaleCycle": {
        "patterns": [
            r"salecycle\.com", r"salecycle", r"sc-static",
            r"salecycleapi"
        ],
        "type": "behavioral_marketing",
        "confidence": 0.80
    },
    "CartStack": {
        "patterns": [
            r"cartstack\.com", r"cartstack", r"cs-static",
            r"cartstackcdn"
        ],
        "type": "cart_recovery",
        "confidence": 0.80
    },
    "Omnisend": {
        "patterns": [
            r"omnisend\.com", r"omnisend", r"omni-",
            r"omnisendcdn"
        ],
        "type": "email_marketing",
        "confidence": 0.85
    },
    "ActiveCampaign": {
        "patterns": [
            r"activecampaign\.com", r"active-campaign", r"vgo",
            r"trackcmp\.net"
        ],
        "type": "email_automation",
        "confidence": 0.85
    },
    "Listrak": {
        "patterns": [
            r"listrak\.com", r"listrak", r"ltktracker",
            r"listrakbi"
        ],
        "type": "cart_recovery",
        "confidence": 0.80
    },
    "Yotpo": {
        "patterns": [
            r"yotpo\.com", r"yotpo", r"yotpo-widget",
            r"staticw2\.yotpo"
        ],
        "type": "reviews_loyalty",
        "confidence": 0.85
    },
    "Smile.io": {
        "patterns": [
            r"smile\.io", r"smile-ui", r"sweettooth",
            r"sweet-tooth"
        ],
        "type": "loyalty_rewards",
        "confidence": 0.80
    }
}
