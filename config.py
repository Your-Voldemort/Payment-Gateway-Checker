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
    
    # Request Settings
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 10))
    MAX_URLS_PER_REQUEST = int(os.getenv('MAX_URLS_PER_REQUEST', 10))
    
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
    
    @classmethod
    def validate(cls):
        """Validate required configuration."""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables")
        if not cls.OWNER_USER_ID:
            raise ValueError("OWNER_USER_ID is not set in environment variables")
        return True

# Payment gateway list
PAYMENT_GATEWAYS = [
    "paypal", "stripe", "braintree", "square", "cybersource", "authorize.net", "2checkout",
    "adyen", "worldpay", "sagepay", "checkout.com", "shopify", "razorpay", "bolt", "paytm",
    "venmo", "pay.google.com", "revolut", "eway", "woocommerce", "upi", "apple.com", "payflow",
    "payeezy", "paddle", "payoneer", "recurly", "klarna", "paysafe", "webmoney", "payeer",
    "payu", "skrill", "affirm", "afterpay", "dwolla", "global payments", "moneris", "nmi",
    "payment cloud", "paysimple", "paytrace", "stax", "alipay", "bluepay", "paymentcloud",
    "clover", "zelle", "google pay", "cashapp", "wechat pay", "transferwise", "stripe connect",
    "mollie", "sezzle", "payza", "gocardless", "bitpay", "sureship",
    "conekta", "fatture in cloud", "payzaar", "securionpay", "paylike", "nexi",
    "kiosk information systems", "adyen marketpay", "forte", "worldline", "payu latam"
]

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
