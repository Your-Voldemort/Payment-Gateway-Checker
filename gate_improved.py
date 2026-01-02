
import time
import telebot
from config import Config
from logger import setup_logger
from gateway_checker import check_url
from user_manager import load_user_ids, save_user_id, get_user_count, is_user_registered
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
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *GATEWAY HUNTER BOT*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"Hey *{first_name}*! 👋\n\n"

        f"I'm your payment gateway detective. Send me\n"
        f"any URL and I'll reveal what's under the hood:\n\n"

        f"  💳  Payment processors\n"
        f"  🛡️  Security features\n"
        f"  🔐  3D Secure / OTP\n"
        f"  ☁️  Cloudflare protection\n\n"

        f"┌─────────────────────┐\n"
        f"│  📌 *QUICK START*        │\n"
        f"├─────────────────────┤\n"
        f"│  1️⃣  /register — Get access   │\n"
        f"│  2️⃣  Send any URL             │\n"
        f"│  3️⃣  Get instant results!     │\n"
        f"└─────────────────────┘\n\n"

        f"💡 _Need help?_ Use /help for the full guide\n\n"

        f"🔍 _Let's uncover those payment secrets!_"
    )

    bot.send_message(message.chat.id, welcome_message, parse_mode='Markdown')


@bot.message_handler(commands=['help'])
def cmd_help(message):
    """Handle /help command."""
    help_message = (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 *GATEWAY HUNTER GUIDE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🚀 *GETTING STARTED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  1️⃣  Register with /register\n"
        f"  2️⃣  Send any URL to analyze\n"
        f"  3️⃣  Review your instant report!\n\n"

        f"💬 *COMMANDS*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  `/start` ─ Welcome screen\n"
        f"  `/register` ─ Activate your access\n"
        f"  `/help` ─ This guide\n"
        f"  `/stats` ─ Bot stats _(owner)_\n"
        f"  `/broadcast` ─ Announcements _(owner)_\n\n"

        f"🔍 *WHAT I DETECT*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"  💳 *Payment Gateways*\n"
        f"       Stripe, PayPal, Braintree,\n"
        f"       Square, Adyen, Razorpay,\n"
        f"       and 400+ more processors\n\n"

        f"  🛡️ *Security Features*\n"
        f"       • Cloudflare protection\n"
        f"       • Captcha systems\n"
        f"       • 3D Secure / Verified by Visa\n"
        f"       • OTP requirements\n"
        f"       • CVV/CVC fields\n\n"

        f"  💼 *Payment Systems*\n"
        f"       Inbuilt checkout detection,\n"
        f"       hosted payment pages,\n"
        f"       and embedded forms\n\n"

        f"📝 *URL FORMAT*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  ✓ `example.com`\n"
        f"  ✓ `www.example.com`\n"
        f"  ✓ `https://example.com`\n"
        f"  ✓ Multiple URLs _(one per line)_\n\n"

        f"⚡ *PRO TIPS*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  • Batch analyze up to 10 URLs\n"
        f"  • Target checkout/payment pages\n"
        f"  • No protocol needed — I add it!\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Created by_ @volde\\_is\\_back\n"
        f"🤖 @UrlDebugger_bot"
    )

    bot.send_message(message.chat.id, help_message, parse_mode='Markdown')


@bot.message_handler(commands=['register'])
def cmd_register(message):
    """Handle /register command."""
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"

    # Save user ID
    if save_user_id(user_id):
        logger.info(f"User {user_id} registered successfully")
        success_message = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ *REGISTRATION COMPLETE*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

            f"Welcome aboard, *{first_name}*! 🎉\n\n"

            f"You now have full access to Gateway Hunter.\n\n"

            f"📝 *HOW TO USE*\n"
            f"Simply send me any URL and I'll analyze it:\n\n"

            f"  • `example.com`\n"
            f"  • `https://shop.example.com`\n"
            f"  • Multiple URLs _(one per line)_\n\n"

            f"💡 *PRO TIP*\n"
            f"_Send up to 10 URLs at once for batch analysis!_\n\n"

            f"🚀 Ready when you are!"
        )
        bot.send_message(message.chat.id, success_message, parse_mode='Markdown')
    else:
        error_message = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ *REGISTRATION FAILED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

            f"Oops! Something went wrong.\n\n"

            f"🔄 *WHAT TO DO*\n"
            f"  • Wait a few seconds\n"
            f"  • Try /register again\n"
            f"  • Contact support if the issue persists\n\n"

            f"_We apologize for the inconvenience._"
        )
        bot.send_message(message.chat.id, error_message, parse_mode='Markdown')


@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    """Handle /stats command (Owner only)."""
    if not is_owner(message.from_user.id):
        unauthorized_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔒 *ACCESS DENIED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"_This command is owner-only_"
        )
        bot.send_message(message.chat.id, unauthorized_msg, parse_mode='Markdown')
        return

    user_count = get_user_count()
    rate_status = "✅ Enabled" if Config.ENABLE_RATE_LIMITING else "❌ Disabled"

    stats_message = (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *BOT STATISTICS*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"👥 *USER BASE*\n"
        f"  Total Users: *{user_count}*\n\n"

        f"⚙️ *CONFIGURATION*\n"
        f"  Bot: @voldeGatewayhunterBot\n"
        f"  Rate Limit: {rate_status}\n"
        f"  Max URLs: *{Config.MAX_URLS_PER_REQUEST}*/request\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_System running smoothly_ ✨"
    )

    bot.send_message(message.chat.id, stats_message, parse_mode='Markdown')


@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    """Handle /broadcast command (Owner only)."""
    if not is_owner(message.from_user.id):
        unauthorized_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔒 *ACCESS DENIED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"_This command is owner-only_"
        )
        bot.send_message(message.chat.id, unauthorized_msg, parse_mode='Markdown')
        logger.warning(f"Unauthorized broadcast attempt by user {message.from_user.id}")
        return

    prompt_msg = (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 *BROADCAST MODE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Send your message now.\n"
        f"_It will be delivered to all users._"
    )
    bot.send_message(message.chat.id, prompt_msg, parse_mode='Markdown')
    bot.register_next_step_handler(message, handle_broadcast)


def handle_broadcast(message):
    """Handle the broadcast message content."""
    if not message.text:
        invalid_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ *BROADCAST CANCELLED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"_Invalid message format_"
        )
        bot.send_message(message.chat.id, invalid_msg, parse_mode='Markdown')
        return

    # Send broadcast
    stats = broadcast_message(message.text)

    result_message = (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ *BROADCAST COMPLETE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📤 *Delivered:* {stats['sent']}\n"
        f"❌ *Failed:* {stats['failed']}\n\n"

        f"_Message sent to all active users_ 📢"
    )

    bot.send_message(message.chat.id, result_message, parse_mode='Markdown')


@bot.message_handler(content_types=['text'])
def handle_text(message):
    """Handle text messages containing URLs."""
    user_id = message.from_user.id

    # Check if user is registered (uses cached lookup - no disk I/O)
    if not is_user_registered(user_id):
        not_registered_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *ACCESS REQUIRED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

            f"You need to register first!\n\n"

            f"👉 Use /register to get access\n"
            f"_It only takes a second_ ✨"
        )
        bot.send_message(message.chat.id, not_registered_msg, parse_mode='Markdown')
        return

    # Check rate limit
    if not rate_limiter.is_allowed(user_id):
        wait_time = rate_limiter.get_wait_time(user_id)
        rate_limit_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ *SLOW DOWN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

            f"Rate limit reached.\n\n"

            f"⏱️ Wait *{wait_time} seconds* and try again\n\n"

            f"_This keeps the bot fast for everyone!_ 🚀"
        )
        bot.send_message(message.chat.id, rate_limit_msg, parse_mode='Markdown')
        return

    # Process URLs - normalize and validate
    raw_urls = [url.strip() for url in message.text.strip().splitlines() if url.strip()]

    if not raw_urls:
        no_urls_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ *NO URLs FOUND*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

            f"Send me URLs to analyze:\n\n"

            f"  ✓ `example.com`\n"
            f"  ✓ `https://example.com`\n"
            f"  ✓ Multiple URLs _(one per line)_"
        )
        bot.send_message(message.chat.id, no_urls_msg, parse_mode='Markdown')
        return

    # Normalize URLs (add https:// if missing)
    urls = [normalize_url(url) for url in raw_urls]

    if len(urls) > Config.MAX_URLS_PER_REQUEST:
        too_many_msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ *TOO MANY URLs*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

            f"📊 *Limit:* {Config.MAX_URLS_PER_REQUEST} URLs\n"
            f"📤 *Sent:* {len(urls)} URLs\n\n"

            f"_Split into smaller batches_ 📦"
        )
        bot.send_message(message.chat.id, too_many_msg, parse_mode='Markdown')
        return

    # Send processing message
    processing_msg = bot.send_message(
        message.chat.id,
        f"⏳ *Analyzing {len(urls)} URL{'s' if len(urls) > 1 else ''}...*\n\n"
        f"🔍 _Scanning for gateways and security features_",
        parse_mode='Markdown'
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
                    results.append(
                        f"┌──────────────────────────\n"
                        f"│ 🌐 `{url[:42] + '...' if len(url) > 45 else url}`\n"
                        f"│ 🔴 *ERROR*\n"
                        f"├──────────────────────────\n"
                        f"│ _{error_display}_\n"
                        f"└──────────────────────────\n\n"
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
                results.append(
                    f"┌──────────────────────────\n"
                    f"│ 🌐 `{url[:42] + '...' if len(url) > 45 else url}`\n"
                    f"│ 🔴 *ERROR*\n"
                    f"├──────────────────────────\n"
                    f"│ _{error_display}_\n"
                    f"└──────────────────────────\n\n"
                )

        return results

    # Run the async function using persistent background event loop
    # This avoids creating/destroying event loops per request
    try:
        results = run_async(process_urls_async(), timeout=60)
    except Exception as e:
        logger.error(f"Error in async processing: {str(e)}")
        results = [
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ *SYSTEM ERROR*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"_{str(e)[:100]}_\n\n"
            f"_Please try again in a moment._"
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
        header = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ ANALYSIS COMPLETE\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Scanned {url_count} URL{'s' if url_count > 1 else ''}\n\n"
        )

        footer = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Powered by @volde_is_back\n"
            f"🤖 @UrlDebugger_bot"
        )

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
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"❌ *TEXT ONLY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"I can only analyze text URLs.\n\n"

        f"📝 *Send URLs as text:*\n"
        f"  • `example.com`\n"
        f"  • `https://example.com`"
    )
    bot.send_message(message.chat.id, media_msg, parse_mode='Markdown')


def main():
    """Main function to start the bot with automatic reconnection."""
    logger.info("Starting bot polling...")
    logger.info(f"Bot username: @voldeGatewayhunterBot")
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
