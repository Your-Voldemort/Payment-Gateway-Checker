# 🤖 Gateway Hunter - Advanced Payment Gateway Scanner

Gateway Hunter is a sophisticated Telegram bot designed for security researchers and developers to analyze websites and identify payment processors, security configurations, and protection systems.

## 🌟 Key Features

- **Advanced Gateway Detection**: Identifies 400+ payment gateways (Stripe, PayPal, Braintree, Adyen, etc.).
- **Security Analysis**: Detects 3D Secure (VbV/MSC), OTP requirements, and CVV/CVC status.
- **Protection System Identification**: Recognizes Cloudflare, Captcha systems, and WAFs.
- **Checkout Type Detection**: Identifies Hosted, Embedded, and Inbuilt payment systems.
- **Performance Optimized**: Built with native async I/O (aiogram 3.x) and persistent connection pooling.
- **Subscription System**: Built-in plan management with crypto payment integration.
- **Atomic Storage**: Safe JSON-based user data storage with memory caching.

## 🚀 Getting Started

### Prerequisites

- Python 3.9 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Owner User ID (from [@userinfobot](https://t.me/userinfobot))

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd "Gateway checker"
   ```

2. **Set up a virtual environment**:
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # Linux/Mac:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   Create a `.env` file in the root directory:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   OWNER_USER_ID=your_id_here
   REQUEST_TIMEOUT=15
   MAX_URLS_PER_REQUEST=10
   ENABLE_RATE_LIMITING=true
   ```

### Running the Bot

```bash
python bot_aiogram.py
```

## 🎯 Bot Commands

- `/start` - Welcome screen and quick start guide.
- `/register` - Create your account and get access.
- `/url <link>` - Scan one or more URLs (separated by space or newline).
- `/buy` - View premium subscription plans and payment details.
- `/subscription` - Check your current plan status and expiry.
- `/help` - Comprehensive guide on commands and detection features.
- `/cancel` - Abort current operation (like broadcast).

**Owner Commands:**
- `/stats` - View real-time bot usage statistics.
- `/broadcast` - Send a message to all registered users.
- `/addsub <user_id> <duration>` - Grant subscription to a user (e.g., `/addsub 12345 1m`).

## 📁 Project Structure

| File | Description |
| :--- | :--- |
| `bot_aiogram.py` | Main entry point using modern aiogram 3.x framework. |
| `gateway_checker.py`| Core async logic for fetching and analyzing URLs. |
| `detection.py` | Advanced detection engine with multi-tier confidence scoring. |
| `config.py` | Extensive library of gateway signatures and bot settings. |
| `user_manager.py` | User persistence with atomic JSON writes and TTL caching. |
| `utils.py` | UI formatting, URL normalization, and regex helpers. |
| `http_client.py` | Shared aiohttp connection pool management. |
| `rate_limiter.py` | Memory-based request throttling. |

## ⚙️ Detection Methodology

The bot uses a tiered detection system to ensure accuracy:
1. **High Confidence**: Identified via JavaScript SDK signatures and CDN-hosted libraries.
2. **Medium Confidence**: Detected via HTML form actions, iframe sources, and data attributes.
3. **Low Confidence**: Identified via keyword matching with strict word boundaries.

## 🛡️ Security

This tool is intended for legal security research and educational purposes only. Always ensure you have permission to scan the target websites.

---
Created by [@volde_is_back](https://t.me/volde_is_back)
