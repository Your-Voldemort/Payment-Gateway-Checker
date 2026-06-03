# Gateway Checker Bot

> **Payment gateway detection made simple.** Analyze websites and identify payment processors, security features, and protection systems with 400+ gateway signatures, 3-tier confidence scoring, and enterprise-grade reliability.

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-0088cc?style=flat-square)](https://docs.aiogram.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Async-first](https://img.shields.io/badge/async--first-architecture-brightgreen?style=flat-square)](#-architecture)

**Quick Links:** [Features](#-key-features) • [Getting Started](#-getting-started) • [Usage](#-usage) • [Architecture](#-architecture) • [Development](#-development)

## ✨ Key Features

### Payment Gateway Detection

- **400+ Gateway Signatures** across 12 categories (Stripe, PayPal, Braintree, Adyen, Razorpay, Klarna, crypto, BNPL, and more)
- **Regional Specialization** for Global, Europe, APAC, Middle East/Africa, and Latin America
- **3-Tier Confidence Scoring**: High (0.95+), Medium (0.70-0.85), Low (0.40-0.50)
- **Fast Pattern Matching** with Aho-Corasick algorithm (10-20x faster than regex)

### Security Analysis

- 3D Secure/Verified by Visa detection
- OTP/SMS verification requirements
- CVV/CVC requirement analysis
- Cloudflare & WAF detection
- Captcha system identification
- Inbuilt payment system detection

### Performance & Reliability

- **Persistent HTTP connection pooling** (100 total, 10 per host)
- **DNS caching** with 5-minute TTL
- **Result caching** with 1-hour TTL
- **Retry logic** with exponential backoff (3 attempts)
- **User agent rotation** with 100+ realistic agents

### Enterprise Features

- **SQLite database** with async operations and scan history
- **Rate limiting** with sliding window (20 msgs/60s default)
- **Subscription management** (1d, 1m, 3m, 6m, 1y plans)
- **Audit logging** for admin actions
- **Bulk scanning** with real-time progress tracking
- **Atomic file operations** for data integrity

## 🚀 Getting Started

### Prerequisites

- **Python 3.9+**
- **Telegram Bot Token** (create at [@BotFather](https://t.me/BotFather))
- **Owner User ID** (find at [@userinfobot](https://t.me/userinfobot))

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd gateway-checker
   ```

2. **Create virtual environment**
   ```bash
   # Windows
   python -m venv tgbot
   .\tgbot\Scripts\activate
   
   # Linux/Mac
   python -m venv tgbot
   source tgbot/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
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

5. **Run the bot**
   ```bash
   python bot_aiogram.py
   ```

The bot will automatically initialize the SQLite database and migrate any existing user data.

## 💡 Usage

### Single URL Scan
```text
/url https://example.com
```

### Multiple URLs (up to 10)
```text
/url stripe.com paypal.com square.com
```

### Bulk Scan from File

1. Create a `.txt` file with URLs (one per line):
   ```
   https://stripe.com
   https://paypal.com
   https://square.com
   ```

2. Upload the file to the bot
3. Reply with `/bulk`
4. Monitor real-time progress

For detailed bulk scanning instructions, see `QUICK_START.md`.

## 🏗️ Architecture

### Core Design

The bot uses an **async-first architecture** built on:
- **aiogram 3.x** for Telegram bot framework
- **aiohttp** for HTTP requests with persistent connection pooling
- **aiosqlite** for async database operations
- **BeautifulSoup 4** for HTML parsing

### Module Overview

| Module | Purpose | Key Features |
|--------|---------|--------------|
| **bot_aiogram.py** | Main entry point (2873 lines) | FSM state management, native async, inline keyboards |
| **detection.py** | Detection engine (1197 lines) | 3-tier confidence scoring, SDK patterns, security analysis |
| **gateway_checker.py** | URL orchestrator | HTTP requests, caching, retry logic, result aggregation |
| **html_parser.py** | HTML analysis (744 lines) | BeautifulSoup parsing of scripts, forms, iframes |
| **config.py** | Configuration (400+ signatures) | Gateway patterns, categories, environment config |
| **database.py** | SQLite layer | Async operations, user mgmt, scan history, statistics |
| **user_manager.py** | User registration | Atomic JSON writes, in-memory cache (60s TTL), migration |
| **http_client.py** | Connection pooling | Singleton aiohttp.ClientSession, DNS caching |
| **rate_limiter.py** | Request throttling | Sliding window algorithm, persistent storage |
| **pattern_matcher.py** | Multi-pattern search | Aho-Corasick (10-20x faster), regex fallback |
| **cache_manager.py** | Result caching | TTL-based expiration, cache invalidation |
| **security.py** | Input validation | URL sanitization, dangerous scheme blocking |
| **audit_log.py** | Action tracking | Database-backed audit trail, indexed queries |
| **logger.py** | Logging | Console + file output, context tracking |

### Data Flow

```
User (Telegram)
    ↓
bot_aiogram.py (FSM + Rate Limiter)
    ↓
gateway_checker.py (Orchestrator)
    ├─ Cache Check (cache_manager.py)
    ├─ HTTP Request (http_client.py) → Connection Pool
    └─ Analysis
        ├─ HTML Parsing (html_parser.py)
        ├─ Detection (detection.py)
        │   ├─ SDK Patterns (High Confidence: 0.95+)
        │   ├─ HTML Structure (Medium: 0.70-0.85)
        │   └─ Keywords (Low: 0.40-0.50)
        └─ Security Checks
    ↓
Result Storage
    ├─ Cache (cache_manager.py)
    └─ Database (database.py)
    ↓
Telegram Response
```

## 🔍 Detection System

### 3-Tier Confidence Scoring

**High Confidence (0.95+)**: SDK detection with < 1% false positive rate
- JavaScript SDK URLs: `js.stripe.com/v3`, `paypal.com/sdk/js`
- SDK initialization: `Stripe('pk_live_...')`, `PayPal.Buttons()`
- Code patterns: `stripe.elements()`, `braintree.hostedFields`

**Medium Confidence (0.70-0.85)**: Structured HTML analysis
- Form attributes: `action="/paypal/checkout"`
- HTML structure: iframe sources, data attributes
- Input fields: type and data-* attributes

**Low Confidence (0.40-0.50)**: Keyword matching (prone to false positives)
- Word boundary patterns: `\bstripe\b` (matches "stripe" but not "pinstripe")
- Text mentions: "Powered by Authorize.net"

### Gateway Categories

The bot detects gateways across 12 specialized categories:

1. **Global Major** - Stripe, PayPal, Braintree, Adyen, Checkout.com, Worldpay, Square, Authorize.Net
2. **Europe** - Mollie, Klarna, SagePay, Worldline, Nexi, Trustly, Giropay, Przelewy24
3. **APAC** - Razorpay, Paytm, 2Checkout, Cashfree, PayU, Alipay, WeChat Pay
4. **Middle East/Africa** - Telr, HyperPay, PayU
5. **Latin America** - Mercado Pago, Conekta, Openpay, PayU
6. **Cryptocurrency** - Coinbase Commerce, BTCPay, Binance Pay, Crypto.com
7. **BNPL** - Klarna, Affirm, Afterpay, Sezzle
8. **B2B Payments** - Bill.com, Tipalti, Coupa, Concur
9. **Digital Wallets** - Apple Pay, Google Pay, Alipay, WeChat Pay
10. **Subscription** - Stripe Billing, Recurly, Zuora, Chargify
11. **Open Banking** - Plaid, Yodlee, Finicity, Trustly
12. **PayFacs** - Stripe Connect, PayPal Commerce Platform, Square Marketplace

### Pattern Matching

When `pyahocorasick` is installed (optional):
- **10-20x faster** multi-pattern searching
- Graceful fallback to regex if library unavailable
- Significantly reduces CPU on large HTML files

## 💾 Data Persistence

### SQLite Database

Async database layer with `aiosqlite` provides:

| Table | Purpose |
|-------|---------|
| **users** | Registration, subscriptions, migration tracking |
| **scan_history** | URL scans, detected gateways, timestamps |
| **rate_limits** | Request tracking for persistence across restarts |
| **gateway_stats** | Aggregated detection statistics |
| **scan_cache** | Result caching with TTL-based expiration |
| **audit_log** | Admin actions and audit trail |

### User Storage with Atomic Writes

**Atomic JSON Writes** prevent corruption during simultaneous writes:
```python
# 1. Serialize to temp file
# 2. Use os.replace() for atomic swap
# 3. Survives power loss during write
```

**In-Memory Cache:**
- Registered user IDs in memory
- 60-second TTL (configurable)
- Automatic invalidation on registration
- ~90% reduction in disk I/O

**Automatic Migration:**
- JSON → SQLite migration on startup
- Old JSON backed up
- Graceful fallback if database unavailable

## 🚦 Rate Limiting

**Sliding Window Algorithm:**
- Tracks request timestamps per user
- Cleans old timestamps outside window
- Persists to database (survives restarts)
- Default: 20 messages per 60 seconds

```env
ENABLE_RATE_LIMITING=true
RATE_LIMIT_MESSAGES=20
RATE_LIMIT_WINDOW=60
```

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
USER_AGENT_TYPE=all  # all, desktop, mobile, chrome, firefox
```

**Subscription & Payments:**
```env
BTC_ADDRESS=bc1qw79l29y4yp2chmwmj3nw4my062a3aazjctx4q6
LTC_ADDRESS=ltc1q8sfrqzsahn7a0gcx6h5304ljf08k4vqvq04sau
USDT_TRC20_ADDRESS=TJpx8Knpv6toy2QKqWdt64W2HxVt7q8gef
```

## 🔒 Security

### Input Validation

- URL sanitization (removes dangerous schemes)
- Text input validation
- Dangerous scheme blocking: `javascript:`, `data:`, `vbscript:`
- Suspicious pattern detection

### Message Safety

- Plain text responses with Unicode emojis (no Markdown for dynamic content)
- Message splitting for large responses (>4096 chars)
- Box-drawing Unicode for visual formatting
- No execution of user-provided code

### Audit Logging

- Database-backed audit trail
- Tracks admin actions (broadcasts, subscriptions)
- Indexed for performance
- Queryable by admin, action type, timestamp

## 📊 Performance

| Metric | Value |
|--------|-------|
| HTTP Connections | 100 total, 10 per host |
| DNS Cache TTL | 5 minutes |
| Result Cache TTL | 1 hour |
| Pattern Matching | 10-20x faster with Aho-Corasick |
| Retry Attempts | 3 with exponential backoff |
| User Agent Pool | 100+ realistic agents |

## 🧪 Testing

Custom test runner (no pytest dependency):

```bash
# Run detection tests
python test_bugs_comprehensive.py

# Tests output [PASS] or [FAIL]
```

Test coverage includes:
- Detection accuracy and confidence scoring
- Database operations and migrations
- Result caching and TTL
- Rate limiting logic
- Audit logging
- Input validation and security
- URL normalization
- Retry mechanism with backoff

## 📖 Development

The project includes comprehensive development documentation:

- **`AGENTS.md`** - Code style, naming conventions, async patterns, type hints
- **`QUICK_START.md`** - Fast reference for installation and setup
- **`IMPROVEMENTS.md`** - Performance optimization notes
- **`gate_implement.md`** - Feature implementation details

### Code Standards

**Import order** (3 groups with blank lines):
```python
# Standard library
import os, re, asyncio

# Third-party
import aiohttp
from bs4 import BeautifulSoup

# Local modules
from config import Config
from logger import setup_logger
```

**Naming conventions:**
- Functions: `snake_case` (`check_url`, `find_payment_gateways`)
- Classes: `PascalCase` (`Config`, `RateLimiter`)
- Constants: `UPPER_SNAKE_CASE` (`PAYMENT_GATEWAYS`, `SDK_PATTERNS`)
- Private: `_leading_underscore` (`_cache`)

**Type hints** (mandatory):
```python
def check_url(url: str) -> Tuple[List[str], int, bool]:
    ...
```

**Docstrings** (Google-style for public functions):
```python
def analyze_url_response(html: str, headers: dict) -> dict:
    """
    Analyze URL response for payment gateways.
    
    Args:
        html: HTML content
        headers: Response headers
        
    Returns:
        Dict with keys: gateways, confidence_scores, cloudflare
    """
```

## 🛠️ Common Tasks

### Add a Payment Gateway

1. Add signature to `config.py` (lines 72-663)
   ```python
   GATEWAYS_GLOBAL = [
       # ... existing gateways
       'newgateway.com/sdk.js',
   ]
   ```

2. (Optional) Add SDK patterns to `detection.py`
   ```python
   SDK_PATTERNS = {
       'newgateway': [r'newgateway\.init\('],
   }
   ```

3. Test: `/url <website-with-gateway>`

### Modify HTTP Behavior

Edit `gateway_checker.py`:
- Retry logic
- Timeouts
- User agent rotation
- Connection pooling

### Customize Rate Limiting

Edit `rate_limiter.py` or `.env`:
- Sliding window algorithm
- Persistence settings
- Default limits

### View Audit Log

Query SQLite database:
```python
import sqlite3
conn = sqlite3.connect('gateway_checker.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 10')
print(cursor.fetchall())
```

## ⚠️ Anti-Patterns to Avoid

1. **NO Markdown for dynamic content** - Use plain text + Unicode (markdown breaks on special chars)
2. **NO `asyncio.run()` in handlers** - Use `run_async()` from `async_manager.py`
3. **NO bare `except:`** - Use specific exception types
4. **NO word-boundary violations** - Use `\bgateway\b` not `gateway`
5. **NO session leaks** - Close aiohttp sessions or use singleton
6. **NO file corruption** - Use atomic writes (temp file + `os.replace()`)

## 📋 Project Structure

```
Gateway Checker/
├── bot_aiogram.py              # Main entry (2873 lines)
├── detection.py                # Detection engine (1197 lines)
├── gateway_checker.py          # HTTP orchestrator
├── html_parser.py              # HTML analysis
├── config.py                   # Signatures + config
├── database.py                 # SQLite async layer
├── user_manager.py             # User registration
├── http_client.py              # Connection pooling
├── cache_manager.py            # Result caching
├── rate_limiter.py             # Request throttling
├── pattern_matcher.py          # Multi-pattern matching
├── security.py                 # Input validation
├── audit_log.py                # Action tracking
├── async_manager.py            # Sync-to-async bridge
├── logger.py                   # Centralized logging
├── progress_tracker.py         # Bulk scan progress
├── utils.py                    # URL normalization
├── user_agents.py              # UA rotation
├── requirements.txt            # Dependencies
├── .env.example                # Config template
├── README.md                   # This file
├── AGENTS.md                   # Development guide
├── QUICK_START.md              # Fast setup
├── IMPROVEMENTS.md             # Optimization notes
├── gate_implement.md           # Implementation guide
└── test_bugs_comprehensive.py  # Test suite
```

## 📦 Dependencies

**Core:**
- `aiogram>=3.24.0` - Telegram bot framework
- `aiohttp==3.9.1` - Async HTTP client
- `beautifulsoup4>=4.12.0` - HTML parsing
- `lxml>=5.0.0` - Fast XML/HTML processor
- `aiosqlite>=0.19.0` - Async SQLite

**Performance (optional):**
- `pyahocorasick>=2.0.0` - 10-20x faster pattern matching

**Other:**
- `python-dotenv==1.0.0` - Environment config
- `validators==0.22.0` - URL validation
- `curl_cffi>=0.6.0` - TLS fingerprint bypass
- `fake-useragent>=2.2.0` - User agent rotation

See `requirements.txt` for pinned versions.

## 🤝 Contributing

Contributions are welcome! Please:

1. Follow code standards in `AGENTS.md`
2. Add tests for new features
3. Test with `/url <test-site>`
4. Submit issues with reproduction steps

## 📝 License

This project is provided as-is for authorized security research and educational purposes only. Always obtain permission before scanning target websites.

## 🙋 Support

For issues, questions, or feature requests:
1. Check existing documentation (`AGENTS.md`, `QUICK_START.md`)
2. Review recent improvements in `IMPROVEMENTS.md`
3. Check test files for usage examples
4. Open an issue with:
   - What you tried
   - What you expected
   - What happened instead
   - Python version + OS

---

**Built with async-first architecture for reliability and scale.** Happy gateway hunting! 🚀
