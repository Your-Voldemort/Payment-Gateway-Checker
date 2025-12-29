# 🤖 Telegram Gateway Hunter Bot

A sophisticated Telegram bot for detecting payment gateways and security features on websites.

## ✨ Features

- 🔍 **Payment Gateway Detection** - Detects 50+ payment gateways
- 🛡️ **Security Analysis** - Identifies Captcha, Cloudflare, 3D Secure, OTP
- 💳 **CVV/CVC Detection** - Analyzes card verification requirements
- 🏗️ **Inbuilt Payment System Detection** - Identifies custom payment solutions
- 📊 **User Management** - Register users and track statistics
- 🚦 **Rate Limiting** - Prevents spam and abuse
- 📢 **Broadcast System** - Send messages to all users (owner only)
- 📝 **Comprehensive Logging** - Detailed logs for debugging and monitoring

## 🚀 Installation

### 1. Clone or Download the Project

```bash
cd "d:\Stuff\Projecta\New folder"
```

### 2. Create Virtual Environment

```bash
python -m venv tgbot
```

### 3. Activate Virtual Environment

**Windows:**

```bash
.\tgbot\Scripts\activate
```

**Linux/Mac:**

```bash
source tgbot/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables

1. Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

1. Edit `.env` and add your credentials:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
OWNER_USER_ID=your_telegram_user_id
```

**How to get your Bot Token:**

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the instructions
3. Copy the API token provided

**How to get your User ID:**

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy the ID number

## 🎯 Usage

### Running the Bot

**Option 1: Using the improved version (Recommended)**

```bash
python gate_improved.py
```

**Option 2: Using the original version**

```bash
python gate.py
```

### Bot Commands

- `/start` - Start the bot and see welcome message
- `/register` - Register to use the bot
- `/help` - Display help information
- `/stats` - View bot statistics (Owner only)
- `/broadcast` - Send message to all users (Owner only)

### Checking URLs

1. Register with `/register`
2. Send one or more URLs (each on a new line):

```
https://example.com/checkout
https://store.example.com/payment
```

1. Receive detailed analysis including:
   - Payment gateways detected
   - Security features (Captcha, Cloudflare, 3D Secure, OTP)
   - CVV/CVC requirements
   - Inbuilt payment system status
   - HTTP status code

## 📁 Project Structure

```
.
├── gate.py                 # Original bot implementation
├── gate_improved.py        # Improved bot implementation (modular)
├── config.py              # Configuration management
├── logger.py              # Logging setup
├── utils.py               # Utility functions
├── gateway_checker.py     # URL checking logic
├── user_manager.py        # User management
├── rate_limiter.py        # Rate limiting
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variables template
└── README.md             # This file
```

## 🔧 Configuration

Edit `.env` to customize:

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather | Required |
| `OWNER_USER_ID` | Your Telegram user ID | Required |
| `REQUEST_TIMEOUT` | HTTP request timeout (seconds) | 10 |
| `MAX_URLS_PER_REQUEST` | Maximum URLs per message | 10 |
| `ENABLE_RATE_LIMITING` | Enable/disable rate limiting | true |
| `RATE_LIMIT_MESSAGES` | Messages allowed per window | 20 |
| `RATE_LIMIT_WINDOW` | Rate limit window (seconds) | 60 |

## 🆚 Differences: Original vs Improved

### Original (`gate.py`)

- ❌ Hardcoded API token (security risk!)
- ❌ No rate limiting
- ❌ Limited error handling
- ❌ No logging
- ❌ Monolithic structure
- ❌ User registration doesn't save users

### Improved (`gate_improved.py`)

- ✅ Environment variable configuration
- ✅ Rate limiting to prevent spam
- ✅ Comprehensive error handling
- ✅ Detailed logging (console + file)
- ✅ Modular architecture
- ✅ Actual user registration
- ✅ Statistics tracking
- ✅ Help command
- ✅ Better UX with processing messages
- ✅ Message length handling for long results

## 🛡️ Security Best Practices

1. **Never commit `.env` file** - Add it to `.gitignore`
2. **Keep your bot token secret** - Don't share it publicly
3. **Regularly update dependencies** - Run `pip install -U -r requirements.txt`
4. **Monitor logs** - Check `bot.log` for suspicious activity
5. **Use rate limiting** - Enabled by default to prevent abuse

## 📊 Monitoring

Logs are written to:

- **Console** - INFO level and above
- **bot.log** - DEBUG level and above

Monitor your bot:

```bash
# View recent logs
tail -f bot.log

# Search for errors
grep "ERROR" bot.log
```

## 🐛 Troubleshooting

**Bot doesn't start:**

- Check if `.env` file exists and contains valid values
- Verify bot token is correct
- Ensure all dependencies are installed

**URLs not checking:**

- Verify user is registered (`/register`)
- Check rate limits
- Look for errors in `bot.log`

**Broadcast not working:**

- Ensure you're using the correct owner user ID
- Verify users have registered

## 🤝 Contributing

Feel free to submit issues or pull requests to improve the bot!
