
import time
import telebot
from config import Config
from logger import setup_logger
from gateway_checker import check_url
from user_manager import load_user_ids, register_user, get_user_count, is_user_registered
from rate_limiter import RateLimiter
from utils import format_url_result, normalize_url
from async_manager import run_async, shutdown_async_manager
from http_client import get_http_session, close_http_client

# Initialize logger
logger = setup_logger()

# Validate configuration
try:
    Config.validate()
except ValueError as e:
    logger.error(f"Configuration error: {str(e)}")
    logger.error("Please check your .env file and ensure all required variables are set.")
    exit(1)

# Initialize bot
bot = telebot.TeleBot(Config.TELEGRAM_BOT_TOKEN)
rate_limiter = RateLimiter()

logger.info("Bot initialized successfully")

# =============================================================================
# UI COMPONENTS - Reusable message building blocks
# =============================================================================

def get_footer() -> str:
    """Get the standard footer for all messages."""
    return (
        "\n"
        "╭───────────────────────────╮\n"
        "│  @volde_is_back           │\n"
        "│  🤖 @UrlDebugger_bot      │\n"
        "╰───────────────────────────╯"
    )


def is_owner(user_id: int) -> bool:
    """Check if user is the bot owner."""
    return user_id == Config.OWNER_USER_ID


def broadcast_message(message: str) -> dict:
    """
    Send a broadcast message to all users.
    
    Args:
        message: The message to broadcast
        
    Returns:
        dict: Statistics about the broadcast (sent, failed)
    """
    user_ids = load_user_ids()
    stats = {'sent': 0, 'failed': 0}
    
    logger.info(f"Broadcasting message to {len(user_ids)} users")
    
    for user_id in user_ids:
        try:
            bot.send_message(user_id, message)
            stats['sent'] += 1
        except Exception as e:
            logger.error(f"Failed to send message to {user_id}: {str(e)}")
            stats['failed'] += 1
    
    logger.info(f"Broadcast complete - Sent: {stats['sent']}, Failed: {stats['failed']}")
    return stats


@bot.message_handler(commands=['start'])
def cmd_start(message):
    """Handle /start command."""
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"

    logger.info(f"User {user_id} ({first_name}) started the bot")

    welcome_message = (
        "╭───────────────────────────╮\n"
        "│   🎯  GATEWAY HUNTER      │\n"
        "│   Payment Gateway Scanner │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Hey {first_name}! 👋\n"
        "\n"
        "I analyze websites to detect payment\n"
        "systems and security configurations.\n"
        "\n"
        "┌─ WHAT I DETECT ───────────\n"
        "│\n"
        "│  💳  Payment Gateways\n"
        "│      Stripe, PayPal, Braintree\n"
        "│      Square, Adyen +400 more\n"
        "│\n"
        "│  🔐  Security Features\n"
        "│      3D Secure, OTP, CVV checks\n"
        "│\n"
        "│  🛡️  Protection Systems\n"
        "│      Cloudflare, Captcha, WAF\n"
        "│\n"
        "│  📦  Checkout Types\n"
        "│      Hosted, Embedded, Inbuilt\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ QUICK START ─────────────\n"
        "│\n"
        "│  ›  /register  ─  Get access\n"
        "│  ›  Send URL   ─  Any website\n"
        "│  ›  Get Report ─  Instant results\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "💡 Type /help for the full guide"
        + get_footer()
    )

    bot.send_message(message.chat.id, welcome_message)


@bot.message_handler(commands=['help'])
def cmd_help(message):
    """Handle /help command."""
    help_message = (
        "╭───────────────────────────╮\n"
        "│   📖  GATEWAY HUNTER      │\n"
        "│   Complete Guide          │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "┌─ ABOUT ───────────────────\n"
        "│\n"
        "│  Gateway Hunter scans websites\n"
        "│  to detect payment processors,\n"
        "│  security features, and protection\n"
        "│  systems used on checkout pages.\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ COMMANDS ────────────────\n"
        "│\n"
        "│  /start     ─  Welcome screen\n"
        "│  /register  ─  Activate access\n"
        "│  /help      ─  This guide\n"
        "│  /stats     ─  Bot statistics ⚡\n"
        "│  /broadcast ─  Announcement ⚡\n"
        "│\n"
        "│  ⚡ = Owner only\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ 💳 PAYMENT GATEWAYS ─────\n"
        "│\n"
        "│  Stripe, PayPal, Braintree,\n"
        "│  Square, Adyen, Razorpay,\n"
        "│  Authorize.net, Worldpay,\n"
        "│  Klarna, Afterpay +400 more\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ 🔐 SECURITY DETECTION ───\n"
        "│\n"
        "│  ›  3D Secure / VbV / MSC\n"
        "│  ›  OTP verification\n"
        "│  ›  CVV/CVC requirements\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ 🛡️ PROTECTION DETECTION ─\n"
        "│\n"
        "│  ›  Cloudflare detection\n"
        "│  ›  Captcha systems\n"
        "│  ›  WAF identification\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ 📦 CHECKOUT TYPES ───────\n"
        "│\n"
        "│  ›  Hosted payment pages\n"
        "│  ›  Embedded checkout forms\n"
        "│  ›  Inbuilt payment systems\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ URL FORMATS ─────────────\n"
        "│\n"
        "│  ✓  example.com\n"
        "│  ✓  www.example.com\n"
        "│  ✓  https://example.com\n"
        "│  ✓  https://shop.com/checkout\n"
        "│\n"
        "│  Send up to 10 URLs at once\n"
        "│  (one per line)\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ PRO TIPS ────────────────\n"
        "│\n"
        "│  ›  Target checkout pages for\n"
        "│     best gateway detection\n"
        "│\n"
        "│  ›  No protocol needed - I'll\n"
        "│     add https:// automatically\n"
        "│\n"
        "│  ›  Batch analyze for speed\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "╭───────────────────────────╮\n"
        "│  Created by @volde_is_back │\n"
        "│  🤖 @UrlDebugger_bot       │\n"
        "╰───────────────────────────╯"
    )

    bot.send_message(message.chat.id, help_message)


@bot.message_handler(commands=['register'])
def cmd_register(message):
    """Handle /register command."""
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"

    # Register user and get status
    status = register_user(user_id)
    
    if status == 'new':
        logger.info(f"User {user_id} registered successfully")
        success_message = (
            "╭───────────────────────────╮\n"
            "│   ✅  ACCESS GRANTED      │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"Welcome aboard, {first_name}! 🎉\n"
            "\n"
            "You now have full access to\n"
            "Gateway Hunter.\n"
            "\n"
            "┌─ HOW TO USE ──────────────\n"
            "│\n"
            "│  Just send me any URL:\n"
            "│\n"
            "│  ›  example.com\n"
            "│  ›  https://shop.example.com\n"
            "│  ›  Multiple URLs (one per line)\n"
            "│\n"
            "└────────────────────────────\n"
            "\n"
            "┌─ LIMITS ──────────────────\n"
            "│\n"
            f"│  ›  {Config.MAX_URLS_PER_REQUEST} URLs per request\n"
            "│  ›  Rate limit applies\n"
            "│\n"
            "└────────────────────────────\n"
            "\n"
            "🚀 Ready! Send your first URL"
            + get_footer()
        )
        bot.send_message(message.chat.id, success_message)
        
    elif status == 'existing':
        logger.info(f"User {user_id} already registered")
        existing_message = (
            "╭───────────────────────────╮\n"
            "│   ℹ️  ALREADY REGISTERED  │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"Hey {first_name}, you're all set! 👋\n"
            "\n"
            "Your account is active.\n"
            "Just send any URL to start scanning.\n"
            "\n"
            "┌─ QUICK ACTIONS ───────────\n"
            "│\n"
            "│  ›  Send a URL to scan\n"
            "│  ›  /help for full guide\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        bot.send_message(message.chat.id, existing_message)
        
    else:  # error
        logger.error(f"Failed to register user {user_id}")
        error_message = (
            "╭───────────────────────────╮\n"
            "│   ❌  REGISTRATION FAILED │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Something went wrong.\n"
            "\n"
            "┌─ TRY THESE STEPS ─────────\n"
            "│\n"
            "│  ›  Wait a few seconds\n"
            "│  ›  Send /register again\n"
            "│  ›  Contact @volde_is_back\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        bot.send_message(message.chat.id, error_message)


@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    """Handle /stats command (Owner only)."""
    if not is_owner(message.from_user.id):
        unauthorized_msg = (
            "╭───────────────────────────╮\n"
            "│   🔒  ACCESS DENIED       │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "This command is owner-only."
            + get_footer()
        )
        bot.send_message(message.chat.id, unauthorized_msg)
        return

    user_count = get_user_count()
    rate_status = "✅ Enabled" if Config.ENABLE_RATE_LIMITING else "❌ Disabled"

    stats_message = (
        "╭───────────────────────────╮\n"
        "│   📊  BOT STATISTICS      │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "┌─ USER BASE ──────────────\n"
        "│\n"
        f"│  Total Users  ›  {user_count}\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ CONFIGURATION ──────────\n"
        "│\n"
        "│  Bot        ›  @UrlDebugger_bot\n"
        f"│  Rate Limit ›  {rate_status}\n"
        f"│  Max URLs   ›  {Config.MAX_URLS_PER_REQUEST}/request\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "✨ System running smoothly"
        + get_footer()
    )

    bot.send_message(message.chat.id, stats_message)


@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    """Handle /broadcast command (Owner only)."""
    if not is_owner(message.from_user.id):
        unauthorized_msg = (
            "╭───────────────────────────╮\n"
            "│   🔒  ACCESS DENIED       │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "This command is owner-only."
            + get_footer()
        )
        bot.send_message(message.chat.id, unauthorized_msg)
        logger.warning(f"Unauthorized broadcast attempt by user {message.from_user.id}")
        return

    prompt_msg = (
        "╭───────────────────────────╮\n"
        "│   📢  BROADCAST MODE      │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Send your message now.\n"
        "\n"
        "It will be delivered to all users."
        + get_footer()
    )
    bot.send_message(message.chat.id, prompt_msg)
    bot.register_next_step_handler(message, handle_broadcast)


def handle_broadcast(message):
    """Handle the broadcast message content."""
    if not message.text:
        invalid_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  BROADCAST CANCELLED │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Invalid message format."
            + get_footer()
        )
        bot.send_message(message.chat.id, invalid_msg)
        return

    # Send broadcast
    stats = broadcast_message(message.text)

    result_message = (
        "╭───────────────────────────╮\n"
        "│   ✅  BROADCAST COMPLETE  │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "┌─ DELIVERY STATS ─────────\n"
        "│\n"
        f"│  📤 Delivered  ›  {stats['sent']}\n"
        f"│  ❌ Failed     ›  {stats['failed']}\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "Message sent to all active users 📢"
        + get_footer()
    )

    bot.send_message(message.chat.id, result_message)


@bot.message_handler(content_types=['text'])
def handle_text(message):
    """Handle text messages containing URLs."""
    user_id = message.from_user.id

    # Check if user is registered (uses cached lookup - no disk I/O)
    if not is_user_registered(user_id):
        not_registered_msg = (
            "╭───────────────────────────╮\n"
            "│   ⚠️  ACCESS REQUIRED     │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You need to register first!\n"
            "\n"
            "┌─ GET STARTED ────────────\n"
            "│\n"
            "│  ›  Use /register to get access\n"
            "│  ›  It only takes a second ✨\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        bot.send_message(message.chat.id, not_registered_msg)
        return

    # Check rate limit
    if not rate_limiter.is_allowed(user_id):
        wait_time = rate_limiter.get_wait_time(user_id)
        rate_limit_msg = (
            "╭───────────────────────────╮\n"
            "│   ⏳  SLOW DOWN           │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Rate limit reached.\n"
            "\n"
            "┌─ PLEASE WAIT ────────────\n"
            "│\n"
            f"│  ⏱️  {wait_time} seconds remaining\n"
            "│\n"
            "│  This keeps the bot fast\n"
            "│  for everyone! 🚀\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        bot.send_message(message.chat.id, rate_limit_msg)
        return

    # Process URLs - normalize and validate
    raw_urls = [url.strip() for url in message.text.strip().splitlines() if url.strip()]

    if not raw_urls:
        no_urls_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  NO URLs FOUND       │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Send me URLs to analyze.\n"
            "\n"
            "┌─ ACCEPTED FORMATS ───────\n"
            "│\n"
            "│  ✓  example.com\n"
            "│  ✓  https://example.com\n"
            "│  ✓  Multiple URLs\n"
            "│     (one per line)\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        bot.send_message(message.chat.id, no_urls_msg)
        return

    # Normalize URLs (add https:// if missing)
    urls = [normalize_url(url) for url in raw_urls]

    if len(urls) > Config.MAX_URLS_PER_REQUEST:
        too_many_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  TOO MANY URLs       │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "┌─ LIMIT EXCEEDED ─────────\n"
            "│\n"
            f"│  📊 Limit  ›  {Config.MAX_URLS_PER_REQUEST} URLs\n"
            f"│  📤 Sent   ›  {len(urls)} URLs\n"
            "│\n"
            "│  Please split into smaller\n"
            "│  batches 📦\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        bot.send_message(message.chat.id, too_many_msg)
        return

    # Send processing message
    url_word = "URL" if len(urls) == 1 else "URLs"
    processing_msg = bot.send_message(
        message.chat.id,
        "╭───────────────────────────╮\n"
        "│   ⏳  SCANNING            │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Analyzing {len(urls)} {url_word}...\n"
        "\n"
        "┌─ CHECKING ────────────────\n"
        "│\n"
        "│  ›  Payment gateways\n"
        "│  ›  Security features\n"
        "│  ›  Protection systems\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "Please wait..."
    )
    
    # Process URLs asynchronously using persistent event loop and connection pool
    import asyncio

    async def process_urls_async():
        """Process all URLs concurrently using persistent HTTP client."""
        results = []

        # Get the shared HTTP session from the persistent client
        session = await get_http_session()

        # Create tasks for all URLs
        tasks = []
        for url in urls:
            logger.info(f"User {user_id} checking URL: {url}")
            tasks.append(check_url(url, session))

        # Execute all checks concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Format results
        for url, response in zip(urls, responses):
            try:
                if isinstance(response, Exception):
                    logger.error(f"Error processing URL {url}: {str(response)}")
                    error_display = str(response)[:50] + "..." if len(str(response)) > 50 else str(response)
                    display_url = url[:24] + "..." if len(url) > 27 else url
                    results.append(
                        "╭─ SCAN RESULT ─────────────╮\n"
                        f"│  🌐 {display_url}\n"
                        "│  🔴 ERROR\n"
                        "╰───────────────────────────╯\n"
                        "\n"
                        "┌─ ❌ ERROR DETAILS ─────────\n"
                        "│\n"
                        f"│  {error_display}\n"
                        "│\n"
                        "└────────────────────────────\n\n"
                    )
                else:
                    detected_gateways, status_code, captcha, cloudflare, payment_security_type, cvv_cvc_status, inbuilt_status = response
                    result_line = format_url_result(
                        url, detected_gateways, status_code, captcha,
                        cloudflare, payment_security_type, cvv_cvc_status, inbuilt_status
                    )
                    results.append(result_line)
            except Exception as e:
                logger.error(f"Error formatting result for {url}: {str(e)}")
                error_display = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
                display_url = url[:24] + "..." if len(url) > 27 else url
                results.append(
                    "╭─ SCAN RESULT ─────────────╮\n"
                    f"│  🌐 {display_url}\n"
                    "│  🔴 ERROR\n"
                    "╰───────────────────────────╯\n"
                    "\n"
                    "┌─ ❌ ERROR DETAILS ─────────\n"
                    "│\n"
                    f"│  {error_display}\n"
                    "│\n"
                    "└────────────────────────────\n\n"
                )

        return results

    # Run the async function using persistent background event loop
    # This avoids creating/destroying event loops per request
    try:
        results = run_async(process_urls_async(), timeout=60)
    except Exception as e:
        logger.error(f"Error in async processing: {str(e)}")
        results = [
            "╭───────────────────────────╮\n"
            "│   ❌  SYSTEM ERROR        │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"{str(e)[:100]}\n"
            "\n"
            "Please try again in a moment."
            + get_footer()
        ]

    # Delete processing message
    try:
        bot.delete_message(message.chat.id, processing_msg.message_id)
    except:
        pass

    # Send results
    if results:
        # Create header based on number of URLs
        url_count = len(urls)
        url_word = "URL" if url_count == 1 else "URLs"
        
        # Pad the URL count line to match header width
        count_text = f"Analyzed {url_count} {url_word}"
        count_padded = count_text + " " * (25 - len(count_text))
        
        header = (
            "╭───────────────────────────╮\n"
            "│   ✅  SCAN COMPLETE       │\n"
            f"│   {count_padded}│\n"
            "╰───────────────────────────╯\n\n"
        )

        footer = get_footer()

        response_message = header + "".join(results) + footer

        # Split message if too long (Telegram limit is 4096 characters)
        # Send as plain text to avoid Markdown parsing issues with dynamic content
        if len(response_message) > 4000:
            for i in range(0, len(response_message), 4000):
                bot.send_message(message.chat.id, response_message[i:i+4000])
        else:
            bot.send_message(message.chat.id, response_message)


@bot.message_handler(content_types=['photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_media(message):
    """Handle media messages."""
    media_msg = (
        "╭───────────────────────────╮\n"
        "│   ❌  TEXT ONLY           │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "I can only analyze text URLs.\n"
        "\n"
        "┌─ SEND URLs AS TEXT ──────\n"
        "│\n"
        "│  ›  example.com\n"
        "│  ›  https://example.com\n"
        "│\n"
        "└────────────────────────────"
        + get_footer()
    )
    bot.send_message(message.chat.id, media_msg)


def main():
    """Main function to start the bot with automatic reconnection."""
    logger.info("Starting bot polling...")
    logger.info(f"Bot username: @UrlDebugger_bot")
    logger.info(f"Owner ID: {Config.OWNER_USER_ID}")

    # Log performance optimization status
    logger.info("Performance optimizations enabled:")
    logger.info("  - Persistent background event loop (no per-request loop creation)")
    logger.info("  - HTTP connection pooling (100 total, 10 per host)")
    logger.info("  - User cache with 60s TTL (reduced disk I/O)")

    # Check for Aho-Corasick availability
    try:
        from pattern_matcher import is_ahocorasick_available
        if is_ahocorasick_available():
            logger.info("  - Aho-Corasick algorithm for fast pattern matching")
        else:
            logger.info("  - Regex-based pattern matching (install pyahocorasick for 10-20x speedup)")
    except ImportError:
        pass

    retry_count = 0
    max_retries = 5
    base_delay = 5  # Base delay in seconds
    max_delay = 60  # Maximum delay between retries

    try:
        while True:
            try:
                logger.info("Bot is now polling for updates...")
                bot.polling(none_stop=True, interval=1, timeout=30)

            except KeyboardInterrupt:
                logger.info("Bot stopped by The Owner (KeyboardInterrupt). Exiting...")
                break

            except telebot.apihelper.ApiException as e:
                # Handle Telegram API specific errors
                logger.error(f"Telegram API error: {str(e)}")
                retry_count += 1

                if retry_count >= max_retries:
                    logger.critical(f"Max retries ({max_retries}) reached. Stopping bot.")
                    break

                # Calculate exponential backoff delay
                delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
                logger.info(f"Retrying in {delay} seconds... (Attempt {retry_count}/{max_retries})")

                time.sleep(delay)

            except Exception as e:
                # Handle all other exceptions (including ReadTimeout)
                error_msg = str(e)
                logger.error(f"Error occurred: {error_msg}")

                # Check if it's a timeout error
                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    logger.warning("Network timeout detected. Attempting to reconnect...")
                    retry_count += 1

                    if retry_count >= max_retries:
                        logger.critical(f"Max retries ({max_retries}) reached after timeout errors. Stopping bot.")
                        break

                    # Calculate exponential backoff delay
                    delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
                    logger.info(f"Reconnecting in {delay} seconds... (Attempt {retry_count}/{max_retries})")

                    time.sleep(delay)
                else:
                    # For non-timeout errors, log and re-raise
                    logger.critical(f"Unexpected error: {error_msg}")
                    logger.exception("Full traceback:")
                    break
            else:
                # Reset retry count on successful connection
                if retry_count > 0:
                    logger.info("Successfully reconnected. Resetting retry counter.")
                    retry_count = 0
    finally:
        # Graceful shutdown of async resources
        logger.info("Shutting down async resources...")
        shutdown_async_manager()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
