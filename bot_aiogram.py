"""
Telegram Gateway Hunter Bot - aiogram 3.x Implementation

This is a native async implementation using aiogram 3.x for maximum performance.
All features from gate_improved.py are preserved with cleaner architecture.

Run with: python bot_aiogram.py
"""

import asyncio
import logging
from typing import List
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Config
from logger import setup_logger
from gateway_checker import check_url
from user_manager import (
    load_user_ids, register_user, get_user_count, is_user_registered,
    check_subscription, add_subscription, get_subscription_expiry
)
from rate_limiter import RateLimiter
from utils import format_url_result, normalize_url
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

# Initialize rate limiter
rate_limiter = RateLimiter()

# Create router for handlers
router = Router()


# =============================================================================
# FSM STATES - For multi-step conversations
# =============================================================================

class BroadcastState(StatesGroup):
    """States for broadcast conversation flow."""
    waiting_for_message = State()


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


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

@router.message(Command("start"))
async def cmd_start(message: Message):
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
        "│  ›  /url <link>─  Scan website\n"
        "│  ›  Get Report ─  Instant results\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "💡 Type /help for the full guide"
        + get_footer()
    )

    await message.answer(welcome_message)


@router.message(Command("help"))
async def cmd_help(message: Message):
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
        "│  /cancel    ─  Cancel operation\n"
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
        "│  ✓  /url example.com\n"
        "│  ✓  /url www.site.com\n"
        "│  ✓  /url https://site.com\n"
        "│  ✓  /url https://site.com/buy\n"
        "│\n"
        "│  Send multiple URLs separated\n"
        "│  by spaces or newlines\n"
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

    await message.answer(help_message)


@router.message(Command("register"))
async def cmd_register(message: Message):
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
            "│  Use the /url command:\n"
            "│\n"
            "│  ›  /url example.com\n"
            "│  ›  /url https://site.com\n"
            "│  ›  Multiple URLs supported\n"
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
        await message.answer(success_message)

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
            "Use /url <link> to start scanning.\n"
            "\n"
            "┌─ QUICK ACTIONS ───────────\n"
            "│\n"
            "│  ›  /url <link> to scan\n"
            "│  ›  /help for full guide\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        await message.answer(existing_message)

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
        await message.answer(error_message)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
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
        await message.answer(unauthorized_msg)
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

    await message.answer(stats_message)


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    """Handle /buy command showing subscription plans."""

    # Plans section
    plans_text = ""
    for duration, details in Config.SUBSCRIPTION_PLANS.items():
        plans_text += f"│  {duration.upper():<3} {details['name']:<10} ›  {details['price']}\n"

    buy_message = (
        "╭───────────────────────────╮\n"
        "│   💎  PREMIUM ACCESS      │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Get unlimited access to the Gateway Hunter.\n"
        "\n"
        "┌─ SUBSCRIPTION PLANS ──────\n"
        "│\n"
        f"{plans_text}"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ PAYMENT METHODS ─────────\n"
        "│\n"
        "│  💰 BTC (Bitcoin)\n"
        f"│  <code>{Config.BTC_ADDRESS}</code>\n"
        "│\n"
        "│  💰 LTC (Litecoin)\n"
        f"│  <code>{Config.LTC_ADDRESS}</code>\n"
        "│\n"
        "│  💰 USDT (TRC20)\n"
        f"│  <code>{Config.USDT_TRC20_ADDRESS}</code>\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "💡 To purchase:\n"
        "1. Send payment to one of the addresses\n"
        "2. Send screenshot to owner @volde_is_back\n"
        "3. Wait for activation"
        + get_footer()
    )

    await message.answer(buy_message, parse_mode=ParseMode.HTML)


@router.message(Command("subscription"))
async def cmd_subscription(message: Message):
    """Check subscription status."""
    user_id = message.from_user.id

    if is_owner(user_id):
        await message.answer(
            "╭───────────────────────────╮\n"
            "│   👑  OWNER ACCESS        │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You have unlimited lifetime access.\n"
            "You are the system administrator."
            + get_footer()
        )
        return

    expiry = get_subscription_expiry(user_id)

    if expiry and expiry > datetime.now():
        time_left = expiry - datetime.now()
        days_left = time_left.days
        hours_left = time_left.seconds // 3600

        status_msg = (
            "╭───────────────────────────╮\n"
            "│   ✅  ACTIVE SUBSCRIPTION │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "┌─ STATUS ──────────────────\n"
            "│\n"
            f"│  Expires  ›  {expiry.strftime('%Y-%m-%d %H:%M')}\n"
            f"│  Remaining›  {days_left}d {hours_left}h\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
    else:
        status_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  NO SUBSCRIPTION     │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You do not have an active plan.\n"
            "\n"
            "Use /buy to view plans and upgrade."
            + get_footer()
        )

    await message.answer(status_msg)


@router.message(Command("addsub"))
async def cmd_addsub(message: Message):
    """Add subscription to user (Owner only). Usage: /addsub <user_id> <duration>"""
    if not is_owner(message.from_user.id):
        return

    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("Usage: /addsub <user_id> <duration>\nExample: /addsub 123456789 1m")
            return

        target_user_id = int(parts[1])
        duration = parts[2]

        new_expiry = add_subscription(target_user_id, duration)

        if new_expiry:
            await message.answer(
                f"✅ Success!\n\n"
                f"User: {target_user_id}\n"
                f"Added: {duration}\n"
                f"New Expiry: {new_expiry}"
            )

            # Optionally notify the user
            try:
                # We need the bot instance to send message to other user
                # In aiogram 3 handlers, message.bot gives access to bot instance
                await message.bot.send_message(
                    target_user_id,
                    "╭───────────────────────────╮\n"
                    "│   🎉  PLAN ACTIVATED      │\n"
                    "╰───────────────────────────╯\n"
                    "\n"
                    f"Your subscription has been extended!\n"
                    f"Expires: {new_expiry}\n"
                    "\n"
                    "Thank you for your support! 💎"
                    + get_footer()
                )
            except Exception as e:
                await message.answer(f"Warning: Could not notify user (user might have blocked bot): {e}")

        else:
            await message.answer("❌ Failed to add subscription. Check logs.")

    except ValueError:
        await message.answer("Invalid format. User ID must be a number.")
    except Exception as e:
        await message.answer(f"Error: {str(e)}")



@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Cancel any ongoing operation."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Nothing to cancel.")
        return

    await state.clear()
    await message.answer(
        "╭───────────────────────────╮\n"
        "│   ❌  CANCELLED           │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Operation cancelled."
        + get_footer()
    )


# =============================================================================
# BROADCAST SYSTEM (FSM-based)
# =============================================================================

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
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
        await message.answer(unauthorized_msg)
        logger.warning(f"Unauthorized broadcast attempt by user {message.from_user.id}")
        return

    # Enter broadcast state
    await state.set_state(BroadcastState.waiting_for_message)

    prompt_msg = (
        "╭───────────────────────────╮\n"
        "│   📢  BROADCAST MODE      │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Send your message now.\n"
        "\n"
        "It will be delivered to all users.\n"
        "\n"
        "Send /cancel to abort."
        + get_footer()
    )
    await message.answer(prompt_msg)


@router.message(BroadcastState.waiting_for_message, F.text)
async def handle_broadcast_message(message: Message, state: FSMContext, bot: Bot):
    """Handle the broadcast message content."""
    # Clear state first
    await state.clear()

    if not message.text:
        invalid_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  BROADCAST CANCELLED │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Invalid message format."
            + get_footer()
        )
        await message.answer(invalid_msg)
        return

    # Send broadcast to all users
    user_ids = load_user_ids()
    stats = {'sent': 0, 'failed': 0}

    logger.info(f"Broadcasting message to {len(user_ids)} users")

    for user_id in user_ids:
        try:
            await bot.send_message(user_id, message.text)
            stats['sent'] += 1
        except Exception as e:
            logger.error(f"Failed to send message to {user_id}: {str(e)}")
            stats['failed'] += 1

    logger.info(f"Broadcast complete - Sent: {stats['sent']}, Failed: {stats['failed']}")

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

    await message.answer(result_message)


# =============================================================================
# URL PROCESSING HANDLER
# =============================================================================

@router.message(Command("url"))
async def cmd_url_check(message: Message, command: CommandObject):
    """Handle /url command to analyze URLs."""
    user_id = message.from_user.id

    # Check for arguments
    if not command.args:
        usage_msg = (
            "╭───────────────────────────╮\n"
            "│   ℹ️  USAGE GUIDE         │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Please provide URLs to scan.\n"
            "\n"
            "┌─ FORMAT ──────────────────\n"
            "│\n"
            "│  /url <link1> [link2] ...\n"
            "│\n"
            "│  Example:\n"
            "│  /url example.com\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        await message.answer(usage_msg)
        return

    # Check if user is registered
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
        await message.answer(not_registered_msg)
        return

    # Check subscription status
    if not check_subscription(user_id):
        payment_required_msg = (
            "╭───────────────────────────╮\n"
            "│   💳  SUBSCRIPTION NEEDED │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You need an active subscription\n"
            "to use the scanner.\n"
            "\n"
            "Use /buy to see plans and prices."
            + get_footer()
        )
        await message.answer(payment_required_msg)
        # Call the buy command handler logic to show plans immediately
        await cmd_buy(message)
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
        await message.answer(rate_limit_msg)
        return

    # Process URLs from command arguments - normalize and validate
    # command.args contains the string after "/url "
    # We split by whitespace to allow multiple URLs separated by space or newline
    raw_urls = [url.strip() for url in command.args.split() if url.strip()]

    if not raw_urls:
        # Should be covered by initial check, but safety net
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
        await message.answer(too_many_msg)
        return

    # Send processing message
    url_word = "URL" if len(urls) == 1 else "URLs"
    processing_msg = await message.answer(
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

    # Process URLs asynchronously - DIRECT AWAIT, no AsyncManager bridge!
    try:
        results = await process_urls_async(urls, user_id)
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
        await processing_msg.delete()
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
            "╰───────────────────────────╯"
        )

        # Send header first
        await message.answer(header)

        # Send each result as a separate message
        footer = get_footer()
        for result in results:
            # Combine result with footer
            # result typically ends with newlines, so strip one set of newlines if needed
            msg_text = result.rstrip() + footer
            await message.answer(msg_text)


async def process_urls_async(urls: List[str], user_id: int) -> List[str]:
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
                display_url = url[:47] + "..." if len(url) > 50 else url
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


# =============================================================================
# MEDIA HANDLER - Reject non-text content
# =============================================================================

@router.message(F.photo | F.video | F.document | F.audio | F.voice | F.sticker)
async def handle_media(message: Message):
    """Handle media messages."""
    media_msg = (
        "╭───────────────────────────╮\n"
        "│   ❌  TEXT ONLY           │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Please use the /url command.\n"
        "\n"
        "┌─ USE COMMAND ────────────\n"
        "│\n"
        "│  ›  /url example.com\n"
        "│  ›  /url https://site.com\n"
        "│\n"
        "└────────────────────────────"
        + get_footer()
    )
    await message.answer(media_msg)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main():
    """Main function to start the bot."""
    logger.info("Starting bot with aiogram 3.x...")
    logger.info(f"Bot username: @UrlDebugger_bot")
    logger.info(f"Owner ID: {Config.OWNER_USER_ID}")

    # Log performance optimization status
    logger.info("Performance optimizations enabled:")
    logger.info("  - Native async (no sync-to-async bridge)")
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

    # Create bot and dispatcher
    bot = Bot(
        token=Config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None)  # Plain text mode
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Include router
    dp.include_router(router)

    # Set up graceful shutdown
    async def on_shutdown():
        """Handle graceful shutdown."""
        logger.info("Shutting down...")
        await close_http_client()
        await bot.session.close()
        logger.info("Shutdown complete.")

    # Register shutdown callback
    dp.shutdown.register(on_shutdown)

    logger.info("Bot is now polling for updates...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError, SystemExit):
        # Clean exit without traceback when Ctrl+C is pressed
        pass
