
import telebot
from config import Config
from logger import setup_logger
from gateway_checker import check_url
from user_manager import load_user_ids, save_user_id, get_user_count
from rate_limiter import RateLimiter
from utils import format_url_result

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
        f"👋 Hey {first_name}! Welcome to Gateway Hunter Bot!\n\n"
        "🔍 I can help you detect payment gateways and security features on websites.\n\n"
        "📝 Use /register to get started\n"
        "❓ Use /help for more information"
    )
    
    bot.send_message(message.chat.id, welcome_message)


@bot.message_handler(commands=['help'])
def cmd_help(message):
    """Handle /help command."""
    help_message = (
        "📖 **Gateway Hunter Bot Help**\n\n"
        "**Available Commands:**\n"
        "/start - Start the bot\n"
        "/register - Register to use the bot\n"
        "/help - Show this help message\n"
        "/stats - Show bot statistics (Owner only)\n"
        "/broadcast - Broadcast message (Owner only)\n\n"
        "**How to use:**\n"
        "1. Use /register to register\n"
        "2. Send one or more URLs (each on a new line)\n"
        "3. Receive detailed analysis of payment gateways and security\n\n"
        "**Features:**\n"
        "✅ Payment gateway detection\n"
        "✅ Captcha detection\n"
        "✅ Cloudflare detection\n"
        "✅ 3D Secure / OTP detection\n"
        "✅ CVV/CVC requirement analysis\n"
        "✅ Inbuilt payment system detection\n\n"
        "Bot by: @volde\\_is\\_back"
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
            "✅ Registration successful!\n\n"
            "You can now send URLs to check payment gateways.\n"
            "Send one or multiple URLs (each on a new line)."
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Registration failed. Please try again later."
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
        f"👥 Total Users: {user_count}\n"
        f"🤖 Bot Username: @voldeGatewayhunterBot\n"
        f"⚙️ Rate Limiting: {'Enabled' if Config.ENABLE_RATE_LIMITING else 'Disabled'}\n"
        f"📝 Max URLs per request: {Config.MAX_URLS_PER_REQUEST}"
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
        f"✅ Broadcast complete!\n\n"
        f"📤 Sent: {stats['sent']}\n"
        f"❌ Failed: {stats['failed']}"
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
            "⚠️ You are not registered. Please use /register first."
        )
        return
    
    # Check rate limit
    if not rate_limiter.is_allowed(user_id):
        wait_time = rate_limiter.get_wait_time(user_id)
        bot.send_message(
            message.chat.id,
            f"⏳ Rate limit exceeded. Please wait {wait_time} seconds before trying again."
        )
        return
    
    # Process URLs
    urls = [url.strip() for url in message.text.strip().splitlines() if url.strip()]
    
    if not urls:
        bot.send_message(message.chat.id, "❌ No URLs provided. Please send valid URLs.")
        return
    
    if len(urls) > Config.MAX_URLS_PER_REQUEST:
        bot.send_message(
            message.chat.id,
            f"❌ Too many URLs. Maximum {Config.MAX_URLS_PER_REQUEST} URLs per request."
        )
        return
    
    # Send processing message
    processing_msg = bot.send_message(
        message.chat.id,
        f"🔄 Processing {len(urls)} URL(s)... Please wait."
    )
    
    results = []
    for url in urls:
        logger.info(f"User {user_id} checking URL: {url}")
        
        try:
            detected_gateways, status_code, captcha, cloudflare, payment_security_type, cvv_cvc_status, inbuilt_status = check_url(url)
            
            result_line = format_url_result(
                url, detected_gateways, status_code, captcha,
                cloudflare, payment_security_type, cvv_cvc_status, inbuilt_status
            )
            results.append(result_line)
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}")
            results.append(f"🔹 URL: {url}\n❌ Error: {str(e)}\n━━━━━━━━━━━━━━\n")
    
    # Delete processing message
    try:
        bot.delete_message(message.chat.id, processing_msg.message_id)
    except:
        pass
    
    # Send results
    if results:
        response_message = (
            "🔍 **Gateways Fetched Successfully** ✅\n"
            "━━━━━━━━━━━━━━\n" +
            "".join(results) +
            "\n👤 Bot by: @volde\\_is\\_back\n"
            "🤖 Bot Username: @voldeGatewayhunterBot"
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
        "❌ I can only process text URLs. Please send URLs as text messages."
    )


def main():
    """Main function to start the bot."""
    logger.info("Starting bot polling...")
    logger.info(f"Bot username: @voldeGatewayhunterBot")
    logger.info(f"Owner ID: {Config.OWNER_USER_ID}")
    
    try:
        bot.polling(none_stop=True, interval=1, timeout=30)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
