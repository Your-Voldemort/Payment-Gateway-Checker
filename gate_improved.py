
import time
import telebot
from config import Config
from logger import setup_logger
from gateway_checker import check_url
from user_manager import load_user_ids, save_user_id, get_user_count
from rate_limiter import RateLimiter
from utils import format_url_result, normalize_url

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
        f"👋 **Hey {first_name}!** Welcome to *Gateway Hunter Bot*\n\n"
        "I help you analyze websites for payment gateways and security features.\n\n"
        "**🚀 Get Started**\n"
        "• Use /register to begin\n"
        "• Use /help for detailed info\n\n"
        "_Let's discover what's behind those payment pages!_ 🔍"
    )
    
    bot.send_message(message.chat.id, welcome_message)


@bot.message_handler(commands=['help'])
def cmd_help(message):
    """Handle /help command."""
    help_message = (
        "📚 **Gateway Hunter Bot** • _Help Guide_\n\n"
        
        "**⚡ Quick Start**\n"
        "1️⃣ Register with /register\n"
        "2️⃣ Send any URL (e.g., `example.com`)\n"
        "3️⃣ Get instant analysis\n\n"
        
        "**🛠️ Available Commands**\n"
        "`/start` - Welcome screen\n"
        "`/register` - Get access to the bot\n"
        "`/help` - Show this guide\n"
        "`/stats` - Bot statistics _(owner only)_\n"
        "`/broadcast` - Send announcements _(owner only)_\n\n"
        
        "**✨ What I Detect**\n"
        "💳 Payment gateways _(Stripe, PayPal, etc.)_\n"
        "🤖 Captcha systems\n"
        "🛡️ Cloudflare protection\n"
        "🔐 3D Secure / OTP requirements\n"
        "🔢 CVV/CVC requirements\n"
        "💼 Inbuilt payment systems\n\n"
        
        "_Bot by_ @volde\\_is\\_back"
    )
    
    bot.send_message(message.chat.id, help_message, parse_mode='Markdown')


@bot.message_handler(commands=['register'])
def cmd_register(message):
    """Handle /register command."""
    user_id = message.from_user.id
    
    # Save user ID
    if save_user_id(user_id):
        logger.info(f"User {user_id} registered successfully")
        bot.send_message(
            message.chat.id,
            "✅ **Registration Successful!**\n\n"
            "You're all set! Send me any URL to analyze.\n\n"
            "**💡 Tip:** _You can send multiple URLs at once_ (one per line)\n"
            "Example: `example.com` or `https://example.com`"
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ **Registration Failed**\n\n"
            "_Something went wrong. Please try again in a moment._"
        )


@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    """Handle /stats command (Owner only)."""
    if not is_owner(message.from_user.id):
        bot.send_message(message.chat.id, "❌ You do not have permission to use this command.")
        return
    
    user_count = get_user_count()
    stats_message = (
        f"📊 **Bot Statistics**\n\n"
        
        f"**👥 User Base**\n"
        f"Total Users: *{user_count}*\n\n"
        
        f"**⚙️ Configuration**\n"
        f"Bot: @voldeGatewayhunterBot\n"
        f"Rate Limiting: *{'✅ Enabled' if Config.ENABLE_RATE_LIMITING else '❌ Disabled'}*\n"
        f"Max URLs/Request: *{Config.MAX_URLS_PER_REQUEST}*\n\n"
        
        f"_System running smoothly_ ✨"
    )
    
    bot.send_message(message.chat.id, stats_message, parse_mode='Markdown')


@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    """Handle /broadcast command (Owner only)."""
    if not is_owner(message.from_user.id):
        bot.send_message(message.chat.id, "❌ You do not have permission to use this command.")
        logger.warning(f"Unauthorized broadcast attempt by user {message.from_user.id}")
        return
    
    bot.send_message(message.chat.id, "📢 Send the message you want to broadcast:")
    bot.register_next_step_handler(message, handle_broadcast)


def handle_broadcast(message):
    """Handle the broadcast message content."""
    if not message.text:
        bot.send_message(message.chat.id, "❌ Invalid message. Broadcast cancelled.")
        return
    
    # Send broadcast
    stats = broadcast_message(message.text)
    
    result_message = (
        f"✅ **Broadcast Complete!**\n\n"
        f"📤 Successfully sent: *{stats['sent']}*\n"
        f"❌ Failed: *{stats['failed']}*\n\n"
        f"_Message delivered to active users_ 📢"
    )
    
    bot.send_message(message.chat.id, result_message)


@bot.message_handler(content_types=['text'])
def handle_text(message):
    """Handle text messages containing URLs."""
    user_id = message.from_user.id
    
    # Check if user is registered
    registered_users = load_user_ids()
    if user_id not in registered_users:
        bot.send_message(
            message.chat.id,
            "⚠️ **Not Registered**\n\n"
            "Please use /register first to access the bot.\n"
            "_It only takes a second!_ ✨"
        )
        return
    
    # Check rate limit
    if not rate_limiter.is_allowed(user_id):
        wait_time = rate_limiter.get_wait_time(user_id)
        bot.send_message(
            message.chat.id,
            f"⏳ **Rate Limit Reached**\n\n"
            f"Please wait *{wait_time} seconds* before trying again.\n\n"
            f"_This helps keep the bot fast for everyone!_ 🚀"
        )
        return
    
    # Process URLs - normalize and validate
    raw_urls = [url.strip() for url in message.text.strip().splitlines() if url.strip()]
    
    if not raw_urls:
        bot.send_message(
            message.chat.id,
            "❌ **No URLs Found**\n\n"
            "Please send one or more URLs to analyze.\n"
            "_Example:_ `example.com` or `https://example.com`"
        )
        return
    
    # Normalize URLs (add https:// if missing)
    urls = [normalize_url(url) for url in raw_urls]
    
    if len(urls) > Config.MAX_URLS_PER_REQUEST:
        bot.send_message(
            message.chat.id,
            f"❌ **Too Many URLs**\n\n"
            f"Maximum *{Config.MAX_URLS_PER_REQUEST} URLs* per request.\n"
            f"You sent: *{len(urls)} URLs*\n\n"
            f"_Please split them into smaller batches_ 📦"
        )
        return
    
    # Send processing message
    processing_msg = bot.send_message(
        message.chat.id,
        f"🔄 **Analyzing {len(urls)} URL{'s' if len(urls) > 1 else ''}**\n\n"
        f"_This may take a moment..._ ⏳"
    )
    
    # Process URLs asynchronously
    import asyncio
    import aiohttp
    
    async def process_urls_async():
        """Process all URLs concurrently."""
        results = []
        
        # Create a shared session for all requests
        async with aiohttp.ClientSession() as session:
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
                        results.append(
                            f"🌐 **URL:** `{url}`\n"
                            f"❌ **Error:** _{str(response)}_\n"
                            f"─────────────────\n"
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
                    results.append(
                        f"🌐 **URL:** `{url}`\n"
                        f"❌ **Error:** _{str(e)}_\n"
                        f"─────────────────\n"
                    )
        
        return results
    
    # Run the async function
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(process_urls_async())
        loop.close()
    except Exception as e:
        logger.error(f"Error in async processing: {str(e)}")
        results = [
            f"❌ **System Error**\n\n"
            f"_{str(e)}_\n"
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
            f"✅ **Analysis Complete!**\n"
            f"_Checked {url_count} URL{'s' if url_count > 1 else ''}_\n"
            f"\n"
        )
        
        response_message = header + "".join(results) + (
            f"\n💬 _Powered by_ @volde\\_is\\_back\n"
            f"🤖 @voldeGatewayhunterBot"
        )
        
        # Split message if too long (Telegram limit is 4096 characters)
        if len(response_message) > 4000:
            for i in range(0, len(response_message), 4000):
                bot.send_message(message.chat.id, response_message[i:i+4000])
        else:
            bot.send_message(message.chat.id, response_message)


@bot.message_handler(content_types=['photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_media(message):
    """Handle media messages."""
    bot.send_message(
        message.chat.id,
        "❌ **Text URLs Only**\n\n"
        "I can only analyze text URLs.\n"
        "_Please send URLs as text messages._ 📝"
    )


def main():
    """Main function to start the bot with automatic reconnection."""
    logger.info("Starting bot polling...")
    logger.info(f"Bot username: @voldeGatewayhunterBot")
    logger.info(f"Owner ID: {Config.OWNER_USER_ID}")
    
    retry_count = 0
    max_retries = 5
    base_delay = 5  # Base delay in seconds
    max_delay = 60  # Maximum delay between retries
    
    while True:
        try:
            logger.info("Bot is now polling for updates...")
            bot.polling(none_stop=True, interval=1, timeout=30)
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
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


if __name__ == "__main__":
    main()
