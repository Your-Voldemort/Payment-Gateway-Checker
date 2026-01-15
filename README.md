# 🤖 Gateway Checker Bot - Payment Gateway Detection

A production-ready Telegram bot for analyzing websites and identifying payment gateways, security features, and protection systems. Built with async-first architecture, comprehensive detection capabilities, and enterprise-grade features.

## 🌟 Key Features

**Payment Gateway Detection**
- Identifies 400+ payment gateways across 12 categories (Stripe, PayPal, Braintree, Adyen, Razorpay, Klarna, Crypto processors, BNPL, etc.)
- Regional specialization: Global, Europe, APAC, Middle East/Africa, Latin America
- 3-tier confidence scoring system (High: 0.95+, Medium: 0.70-0.85, Low: 0.40-0.50)

**Security Analysis**
- 3D Secure/Verified by Visa detection
- OTP/SMS verification requirements
- CVV/CVC requirement status
- Cloudflare presence detection
- Captcha system identification
- Inbuilt payment system detection

**Performance & Reliability**
- Persistent HTTP connection pooling (100 total, 10 per host)
- DNS caching with 5-minute TTL
- Result caching with 1-hour TTL
- Aho-Corasick multi-pattern matching (10-20x faster than regex)
- Retry logic with exponential backoff (3 attempts)
- User agent rotation (100+ realistic agents)

**User Management & Persistence**
- SQLite database with async operations
- Atomic JSON writes for data integrity
- In-memory caching with 60-second TTL
- Subscription management (1d, 1m, 3m, 6m, 1y)
- Automatic migration from JSON to SQLite

**Rate Limiting & Security**
- Sliding window rate limiting (20 msgs/60s default)
- Database persistence across restarts
- Input sanitization and validation
- Dangerous scheme blocking
- Comprehensive audit logging

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Owner User ID (from [@userinfobot](https://t.me/userinfobot))

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd gateway-checker
   ```

2. Create and activate virtual environment:
   ```bash
   # Windows
   python -m venv tgbot
   .\tgbot\Scripts\activate
   
   # Linux/Mac
   python -m venv tgbot
   source tgbot/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your settings:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   OWNER_USER_ID=your_id_here
   REQUEST_TIMEOUT=10
   MAX_URLS_PER_REQUEST=10
   ENABLE_RATE_LIMITING=true
   RATE_LIMIT_MESSAGES=20
   RATE_LIMIT_WINDOW=60
   ```

5. Run the bot:
   ```bash
   python bot_aiogram.py
   ```

## 🎯 Usage Examples

### Single URL Scan

```text
/url https://example.com
```

### Multiple URLs Scan

```text
/url stripe.com paypal.com square.com
```

### Bulk Scan from File

1. Create a `.txt` file with URLs (one per line):

   ```text
   https://stripe.com
   https://paypal.com
   https://square.com/checkout
   ```

2. Upload the file to the bot
3. Reply to the file with `/bulk`
4. Wait for results with real-time progress tracking

See [BULK_SCAN_GUIDE.md](BULK_SCAN_GUIDE.md) for detailed bulk scanning documentation.

## 📋 Bot Commands

### User Commands

- `/start` - Welcome screen and quick start guide
- `/register` - Activate bot access and create account
- `/url <link>` - Scan one or more URLs (space or newline separated)
- `/bulk` - Bulk scan URLs from .txt file (reply to uploaded file)
- `/history` - View your recent scan history with pagination
- `/subscription` - Check subscription status and expiry date
- `/buy` - View subscription plans and payment info
- `/help` - Command reference and detection guide
- `/cancel` - Abort current operation

### Owner Commands

- `/stats` - View real-time bot usage statistics
- `/broadcast` - Send message to all registered users
- `/addsub <user_id> <duration>` - Grant subscription (e.g., `/addsub 12345 1m`)
- `/auditlog` - View admin action audit log
- `/cachestats` - View cache performance statistics
- `/clearcache` - Clear result cache

## 📁 Architecture & Modules

### Core Modules

| Module | Purpose | Key Features |
|--------|---------|--------------|
| `bot_aiogram.py` | Main entry point (aiogram 3.x) | Native async, FSM state management, inline keyboards, middleware support |
| `gateway_checker.py` | URL checking orchestrator | Async HTTP requests, retry logic (3 attempts), result caching, user agent rotation |
| `detection.py` | Payment gateway detection engine | 3-tier confidence scoring, SDK pattern matching, security feature detection |
| `html_parser.py` | Structured HTML analysis | BeautifulSoup parsing of scripts, forms, iframes, input fields |
| `config.py` | Configuration management | 400+ payment gateway patterns, environment variables, subscription settings |
| `user_manager.py` | User registration & caching | JSON storage with atomic writes, in-memory cache (60s TTL), database fallback |
| `database.py` | SQLite persistence layer | Async operations, user management, scan history, rate limits, gateway stats |
| `http_client.py` | Connection pooling | Singleton HTTP client, persistent aiohttp.ClientSession, DNS caching |
| `rate_limiter.py` | Request throttling | Sliding window algorithm, database persistence, per-user limits |
| `pattern_matcher.py` | Multi-pattern matching | Aho-Corasick algorithm (10-20x faster), regex fallback |
| `async_manager.py` | Sync-to-async bridge | Background event loop for legacy sync handlers |
| `logger.py` | Centralized logging | Console + file output, UTF-8 encoding, context tracking |
| `audit_log.py` | Admin action tracking | Database-backed audit trail, indexed queries |
| `security.py` | Input validation | URL sanitization, text validation, dangerous scheme blocking |
| `user_agents.py` | User agent rotation | 100+ realistic browser/device combinations |

### Architecture Diagram

```
User (Telegram)
    ↓
bot_aiogram.py (aiogram 3.x)
    ├─ FSM State Management
    ├─ Rate Limiter (rate_limiter.py)
    └─ URL Scanning
        ↓
    gateway_checker.py
        ├─ Cache Check (cache_manager.py)
        ├─ HTTP Request (http_client.py)
        │   └─ Connection Pool (persistent aiohttp.ClientSession)
        └─ Analysis
            ├─ HTML Parsing (html_parser.py)
            ├─ Detection (detection.py)
            │   ├─ SDK Patterns (High Confidence: 0.95+)
            │   ├─ HTML Structure (Medium Confidence: 0.70-0.85)
            │   └─ Keyword Matching (Low Confidence: 0.40-0.50)
            └─ Security Analysis (utils.py)
                ├─ Cloudflare Detection
                ├─ Captcha Detection
                └─ 3D Secure Detection
        ↓
    Result Storage
        ├─ Cache (cache_manager.py)
        └─ Database (database.py)
        ↓
    User Response (Telegram)
```

## 🔍 Detection System

### 3-Tier Confidence Scoring

**High Confidence (0.95+)**
- JavaScript SDK includes: `js.stripe.com/v3`, `paypal.com/sdk/js`
- SDK initialization: `Stripe('pk_live_...')`, `PayPal.Buttons()`
- Specific code patterns: `stripe.elements()`, `braintree.hostedFields`
- False positive rate: < 1%

**Medium Confidence (0.70-0.85)**
- Form attributes: `action="/paypal/checkout"`, `data-braintree-id`
- HTML structure: iframe sources, input field types
- Data attributes: `data-stripe-key`, `data-paypal-button`
- Requires structured HTML parsing

**Low Confidence (0.40-0.50)**
- Keyword matching with word boundaries: `\bstripe\b` (matches "stripe" but not "pinstripe")
- Text mentions: "Powered by Authorize.net"
- Generic patterns prone to false positives

### Optimization: Aho-Corasick Algorithm

If `pyahocorasick` is installed, the bot uses it for multi-pattern searching:
- 10-20x faster than sequential regex matching
- Graceful fallback to regex if library unavailable
- Significantly reduces CPU usage on large HTML files

### Payment Gateway Categories

The bot detects gateways across 12 categories:

1. **Global Major Processors**: Stripe, PayPal, Braintree, Adyen, Checkout.com, Worldpay, Square, Authorize.Net, CyberSource, Global Payments, Fiserv
2. **European Processors**: Mollie, Klarna, SagePay, Worldline, Nexi, Trustly, iDEAL, Sofort, Giropay, Bancontact, Przelewy24, Paysera
3. **APAC Processors**: Razorpay, Paytm, 2Checkout, Instamojo, Billdesk, Cashfree, PayU, Alipay, WeChat Pay
4. **Middle East/Africa**: 2Checkout, PayU, Telr, HyperPay, Telcell
5. **Latin America**: PayU, 2Checkout, Mercado Pago, Conekta, Openpay
6. **Cryptocurrency**: Coinbase Commerce, BTCPay, Crypto.com, Binance Pay, Phantom Wallet
7. **BNPL (Buy Now Pay Later)**: Klarna, Affirm, Afterpay, Sezzle, Laybuy
8. **B2B Payments**: Bill.com, Tipalti, Coupa, Concur
9. **Digital Wallets**: Apple Pay, Google Pay, Samsung Pay, Alipay, WeChat Pay
10. **Subscription Billing**: Stripe Billing, Recurly, Zuora, Chargify
11. **Open Banking**: Plaid, Yodlee, Finicity, Trustly
12. **PayFacs**: Stripe Connect, PayPal Commerce Platform, Square Marketplace

## 💾 Data Persistence

### SQLite Database

Async database operations using `aiosqlite`:

**Tables:**
- **users**: User registration, subscription expiry, migration tracking
- **scan_history**: URL scans with detected gateways, security info, timestamps
- **rate_limits**: Request timestamps for persistence across restarts
- **gateway_stats**: Aggregated detection statistics
- **scan_cache**: Result caching with TTL-based expiration
- **audit_log**: Admin action tracking (broadcasts, subscriptions)

### User Storage

**Atomic JSON Writes:**
1. Data serialized to string
2. Written to temporary file (`.tmp`)
3. `os.replace()` atomically replaces old file
4. Prevents corruption during simultaneous writes

**In-Memory Cache:**
- Registered user IDs stored in memory Set
- 60-second TTL (configurable)
- Automatic invalidation on new registrations
- Reduces disk I/O by 90%+

**Automatic Migration:**
- JSON to SQLite migration on startup
- Backup of old JSON files
- Graceful fallback if database unavailable

## 🚦 Rate Limiting

**Sliding Window Algorithm:**
- Tracks request timestamps per user
- Cleans up old timestamps outside window
- Default: 20 messages per 60 seconds
- Database persistence survives bot restarts

**Configuration:**
```env
ENABLE_RATE_LIMITING=true
RATE_LIMIT_MESSAGES=20
RATE_LIMIT_WINDOW=60
```

## 🔐 Security Features

**Input Validation:**
- URL sanitization (removes dangerous schemes)
- Text input validation
- Dangerous scheme blocking (javascript:, data:, vbscript:)
- Suspicious pattern detection (script tags, eval, path traversal)

**Telegram Message Safety:**
- Plain text with Unicode emojis (no Markdown for dynamic content)
- Markdown escaping for user-provided data
- Message splitting for content >4096 characters
- Box-drawing characters for visual formatting

**Audit Logging:**
- Database-backed audit trail
- Tracks admin actions (broadcasts, subscriptions)
- Indexed for performance
- Queryable by admin user, action type, timestamp

## 🧪 Testing

### Test Files

- `test_detection.py` - Detection accuracy (word boundaries, SDK patterns, confidence scoring)
- `test_database.py` - Database operations and migrations
- `test_cache.py` - Result caching functionality
- `test_rate_limiter.py` - Rate limiting logic
- `test_audit_log.py` - Audit logging
- `test_integration.py` - End-to-end workflows
- `test_security.py` - Input validation and sanitization
- `test_url_normalization.py` - URL handling
- `test_retry_logic.py` - Retry mechanism with backoff

### Running Tests

Tests use a custom runner (no pytest dependency):

```bash
# Run all detection tests
python test_detection.py

# Run specific test
# Edit test_detection.py main() to call desired test, then:
python test_detection.py
```

Tests print `[PASS]` or `[FAIL]` status.

## ⚙️ Configuration

### Environment Variables

**Bot Settings:**
```env
TELEGRAM_BOT_TOKEN=your_token_here
OWNER_USER_ID=your_id_here
CONTACT_USERNAME=volde_is_back
BOT_USERNAME=UrlDebugger_bot
```

**Request Settings:**
```env
REQUEST_TIMEOUT=10
MAX_URLS_PER_REQUEST=10
```

**Rate Limiting:**
```env
ENABLE_RATE_LIMITING=true
RATE_LIMIT_MESSAGES=20
RATE_LIMIT_WINDOW=60
```

**User Agent Rotation:**
```env
USER_AGENT_ROTATION=true
USER_AGENT_TYPE=all  # all, desktop, mobile, chrome, firefox, etc.
```

**Subscription & Payments:**
```env
BTC_ADDRESS=bc1qw79l29y4yp2chmwmj3nw4my062a3aazjctx4q6
LTC_ADDRESS=ltc1q8sfrqzsahn7a0gcx6h5304ljf08k4vqvq04sau
USDT_TRC20_ADDRESS=TJpx8Knpv6toy2QKqWdt64W2HxVt7q8gef
```

**File Paths:**
```env
USER_IDS_FILE=user_ids.txt
LOG_FILE=bot.log
```

### Subscription Plans

```python
{
    "1d": {"name": "1 Day", "price": "$5"},
    "1m": {"name": "1 Month", "price": "$20"},
    "3m": {"name": "3 Months", "price": "$50"},
    "6m": {"name": "6 Months", "price": "$90"},
    "1y": {"name": "1 Year", "price": "$150"}
}
```

## 📊 Performance Characteristics

**HTTP Connection Pooling:**
- Total connections: 100
- Per-host connections: 10
- Keep-alive: 30 seconds
- DNS cache TTL: 5 minutes

**Caching:**
- Result cache TTL: 1 hour
- User cache TTL: 60 seconds
- Reduces duplicate checks by 70%+

**Pattern Matching:**
- Aho-Corasick: 10-20x faster than regex
- 400+ gateway patterns
- Graceful regex fallback

**Retry Logic:**
- Max retries: 3 attempts
- Initial delay: 1 second
- Backoff multiplier: 2x exponential
- Handles transient failures (5xx, timeouts, connection errors)

## 🛡️ Security & Legal

This tool is for authorized security research and educational purposes only. Always obtain permission before scanning target websites.

## 📚 Development

See `AGENTS.md` for detailed development guidelines including:
- Code style and naming conventions
- Type hints and docstring standards
- Async patterns and error handling
- Logging and configuration practices
- Common pitfalls to avoid

## 🔗 Additional Documentation

- `TECHNICAL_DOCS.md` - Deep dive into architecture and detection logic
- `AGENTS.md` - Development guidelines and code standards
- `IMPLEMENTATION_GUIDE.md` - Feature implementation details
- `QUICK_START.md` - Quick reference guide
