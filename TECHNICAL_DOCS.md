# 📘 Technical Documentation: Gateway Hunter

This document provides a deep dive into the architecture, detection logic, and data flow of the Gateway Hunter Telegram bot.

## 🏗️ Architecture Analysis

### 1. Hybrid Sync-Async Pattern (`gate_improved_old.py`)
This legacy pattern was used to bridge the synchronous `pyTelegramBotAPI` (telebot) with asynchronous I/O.
- **The Challenge**: Telebot handlers block the main polling thread during long-running network requests.
- **The Solution**: Offloading URL processing to a persistent `asyncio` event loop running in a dedicated background thread (`async_manager.py`).
- **Mechanism**:
    1. Message received by sync handler.
    2. Request parameters passed to `run_async()`.
    3. Background loop executes `aiohttp` requests and analysis.
    4. Sync handler waits (blocks) until the background task completes or times out.
    5. Result returned to user.

### 2. Native Async Framework (`bot_aiogram.py`)
The modern implementation utilizes `aiogram 3.x`, a fully asynchronous framework.
- **Advantages**:
    - **Efficiency**: No thread switching or blocking. The entire application runs on a single event loop.
    - **Concurrency**: Naturally handles hundreds of simultaneous requests.
    - **State Management**: Uses aiogram's FSM (Finite State Machine) for complex flows like broadcasts.
    - **Middlewares**: Allows for clean implementation of rate limiting and registration checks.

## 🔍 Detection Engine (`detection.py`)

The bot employs a **3-Tier Confidence Scoring System** to minimize false positives while maximizing detection range.

### Tier 1: High Confidence (Score: 0.95+)
- **Targets**: Script inclusions and CDN URLs.
- **Example**: `<script src="https://js.stripe.com/v3"></script>`
- **Logic**: If a verified payment SDK is loaded, the gateway is definitely present.

### Tier 2: Medium Confidence (Score: 0.70 - 0.85)
- **Targets**: HTML structure and attributes.
- **Example**: `form action=".../paypal/checkout"` or `data-braintree-id`.
- **Logic**: Uses BeautifulSoup (`html_parser.py`) to extract structured elements. Finding a gateway-specific form action or data attribute is a very strong indicator.

### Tier 3: Low Confidence (Score: 0.40 - 0.50)
- **Targets**: Keyword matching.
- **Example**: "Powered by Authorize.net"
- **Logic**: Uses regex with strict word boundaries (`\b`) to avoid matching substrings (e.g., matching "stripe" but not "pinstripe").

### Optimization: Aho-Corasick Algorithm
If `pyahocorasick` is installed, the bot uses it for multi-pattern searching, which is up to 20x faster than sequential regex matching across large HTML files.

## 🔄 Data Flow

1. **Input**: User sends `/url example.com`.
2. **Normalization**: `normalize_url()` ensures the URL has a protocol (`https://`).
3. **Validation**: Check for registration and rate limits.
4. **Session**: Retrieves a shared `aiohttp.ClientSession` from `http_client.py` (utilizes connection pooling).
5. **Request**: Fetches HTML content with rotated User-Agents.
6. **Analysis**:
    - `html_parser.py` extracts scripts, forms, and iframes.
    - `detection.py` runs tiered checks against extracted elements and raw text.
    - `utils.py` checks for Cloudflare, Captcha, and 3D Secure keywords.
7. **Aggregation**: `gateway_checker.py` compiles findings into a standardized result object.
8. **Formatting**: `utils.py` transforms raw data into a visual "card" format for Telegram.

## 💾 Storage & Persistence (`user_manager.py`)

### Atomic JSON Storage
To prevent data corruption during simultaneous writes:
1. Data is serialized to a string.
2. Written to a temporary file (`.tmp`).
3. `os.replace()` (an atomic operation on most OSs) replaces the old JSON with the new one.

### Memory Caching (`UserCache`)
To avoid expensive disk reads on every message:
- Registered user IDs are stored in a `Set` in memory.
- **TTL (Time To Live)**: Cache expires after 60 seconds by default.
- **Invalidation**: New registrations immediately update the cache to ensure instant access.

## 🚦 Throttling (`rate_limiter.py`)

Uses a sliding window algorithm implemented via an in-memory `defaultdict(list)`.
- Tracks timestamps of user requests.
- Cleans up old timestamps outside the `RATE_LIMIT_WINDOW`.
- Rejection occurs if `len(timestamps) > RATE_LIMIT_MESSAGES`.

---
*Document Version: 1.1*
*Last Updated: 2026-01-05*
