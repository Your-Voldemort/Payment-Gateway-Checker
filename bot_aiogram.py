"""
Telegram Gateway Hunter Bot - aiogram 3.x Implementation

This is a native async implementation using aiogram 3.x for maximum performance.
All features from gate_improved.py are preserved with cleaner architecture.

Run with: python bot_aiogram.py
"""

import asyncio
import logging
import signal
from typing import List, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from fsm_storage import SQLiteStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Config
from logger import setup_logger
from gateway_checker import check_url
from user_manager import (
    async_register_user, async_get_user_count, async_is_user_registered,
    async_check_subscription, async_add_subscription, async_get_subscription_expiry,
    async_get_all_user_ids, async_migrate_to_database
)
from rate_limiter import RateLimiter
from utils import format_url_result, normalize_url
from http_client import get_http_session, close_http_client
from security import sanitize_url, sanitize_text_input, validate_duration
from audit_log import log_admin_action, get_audit_logs, get_audit_log_stats
from progress_tracker import ScanProgress

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


class ScanState(StatesGroup):
    """States for URL scanning flow."""
    waiting_for_url = State()


class ScanCache(StatesGroup):
    """Cache for recent scans."""
    last_urls = State()


# =============================================================================
# UI COMPONENTS - Reusable message building blocks
# =============================================================================

def get_footer() -> str:
    """Get the standard footer for all messages."""
    return (
        "\n"
        "╭───────────────────────────╮\n"
        f"│  @{Config.CONTACT_USERNAME:<20}│\n"
        f"│  🤖 @{Config.BOT_USERNAME:<17}│\n"
        "╰───────────────────────────╯"
    )


def is_owner(user_id: int) -> bool:
    """Check if user is the bot owner."""
    return user_id == Config.OWNER_USER_ID


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get the main menu inline keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Scan Website", callback_data="scan_url"),
            InlineKeyboardButton(text="💎 Subscribe", callback_data="subscription")
        ],
        [
            InlineKeyboardButton(text="📖 Help", callback_data="help"),
            InlineKeyboardButton(text="ℹ️ About", callback_data="about")
        ]
    ])
    return keyboard


def get_owner_menu_keyboard() -> InlineKeyboardMarkup:
    """Get owner menu with additional admin options."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Scan Website", callback_data="scan_url"),
            InlineKeyboardButton(text="💎 Subscribe", callback_data="subscription")
        ],
        [
            InlineKeyboardButton(text="📊 Statistics", callback_data="stats"),
            InlineKeyboardButton(text="📢 Broadcast", callback_data="broadcast_start")
        ],
        [
            InlineKeyboardButton(text="📖 Help", callback_data="help"),
            InlineKeyboardButton(text="ℹ️ About", callback_data="about")
        ]
    ])
    return keyboard


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Get back to menu button."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="back_main")]
    ])
    return keyboard


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command with interactive menu."""
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
        "💡 Choose an action below:"
        + get_footer()
    )

    # Choose keyboard based on user role
    keyboard = get_owner_menu_keyboard() if is_owner(user_id) else get_main_menu_keyboard()

    await message.answer(welcome_message, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command with interactive menu."""
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
        "│  /url <link> ─  Scan website\n"
        "│  /bulk     ─  Bulk scan .txt file\n"
        "│  /history   ─  View scan history\n"
        "│  /stats     ─  Bot statistics ⚡\n"
        "│  /auditlog  ─  Admin action log ⚡\n"
        "│  /broadcast ─  Announcement ⚡\n"
        "│  /cancel    ─  Cancel operation\n"
        "│\n"
        "│  ⚡ = Owner only\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "💡 Click below for detailed guides:"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Getting Started", callback_data="help_start")],
        [InlineKeyboardButton(text="🔍 How to Scan", callback_data="help_scan")],
        [InlineKeyboardButton(text="💳 Payment Gateways", callback_data="help_gateways")],
        [InlineKeyboardButton(text="🔐 Security Features", callback_data="help_security")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
    ])

    await message.answer(help_message, reply_markup=keyboard)


@router.message(Command("register"))
async def cmd_register(message: Message):
    """Handle /register command with buttons."""
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"

    # Register user and get status
    status = await async_register_user(user_id, message.from_user.username, first_name)

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
            "┌─ NEXT STEPS ──────────────\n"
            "│\n"
            "│  1️⃣ Subscribe to a plan\n"
            "│  2️⃣ Start scanning URLs\n"
            "│  3️⃣ Get instant results\n"
            "│\n"
            "└────────────────────────────\n"
            "\n"
            "🚀 Ready to get started!"
            + get_footer()
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 View Plans", callback_data="subscription")],
            [InlineKeyboardButton(text="🔍 Start Scanning", callback_data="scan_url")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
        ])

        await message.answer(success_message, reply_markup=keyboard)

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
            "\n"
            "What would you like to do?"
            + get_footer()
        )

        keyboard = get_main_menu_keyboard()
        await message.answer(existing_message, reply_markup=keyboard)

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
            f"│  ›  Contact @{Config.CONTACT_USERNAME}\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Try Again", callback_data="register")],
            [InlineKeyboardButton(text="💬 Contact Support", url=f"https://t.me/{Config.CONTACT_USERNAME}")]
        ])

        await message.answer(error_message, reply_markup=keyboard)


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

    user_count = await async_get_user_count()
    rate_status = "✅ Enabled" if Config.ENABLE_RATE_LIMITING else "❌ Disabled"
    rl_stats = rate_limiter.get_stats()

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
        f"│  Bot        ›  @{Config.BOT_USERNAME}\n"
        f"│  Rate Limit ›  {rate_status}\n"
        f"│  Max URLs   ›  {Config.MAX_URLS_PER_REQUEST}/request\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ RATE LIMITER MEMORY ────\n"
        "│\n"
        f"│  Tracked Users  ›  {rl_stats['tracked_users']}\n"
        f"│  Max Allowed    ›  {rl_stats['max_users']:,}\n"
        f"│  Pending Writes ›  {rl_stats['dirty_users']}\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "✨ System running smoothly"
        + get_footer()
    )

    await message.answer(stats_message)



@router.message(Command("auditlog"))
async def cmd_auditlog(message: Message):
    """Handle /auditlog command (Owner only) - View admin action logs."""
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

    # Get audit log statistics
    stats = await get_audit_log_stats()
    
    # Get recent logs
    logs = await get_audit_logs(limit=10)
    
    # Build header with statistics
    header = (
        "╭───────────────────────────╮\n"
        "│   📋  AUDIT LOG           │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "┌─ STATISTICS ─────────────\n"
        "│\n"
        f"│  Total Entries  ›  {stats['total_entries']}\n"
        f"│  Last 24 Hours  ›  {stats['last_24h']}\n"
        "│\n"
        "└────────────────────────────\n"
    )
    
    # Build actions summary
    if stats['actions_by_type']:
        header += "\n┌─ ACTIONS BY TYPE ────────\n│\n"
        for action, count in stats['actions_by_type'].items():
            header += f"│  {action.capitalize():<12}›  {count}\n"
        header += "│\n└────────────────────────────\n"
    
    # Build recent logs list
    if logs:
        header += "\n┌─ RECENT ACTIONS ─────────\n│\n"
        for log in logs[:5]:  # Show only 5 most recent
            # Parse timestamp
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(log['timestamp'])
                time_str = ts.strftime("%m/%d %H:%M")
            except:
                time_str = "N/A"
            
            action_emoji = {
                'broadcast': '📢',
                'addsub': '💎',
                'admin': '⚙️'
            }.get(log['action'], '📝')
            
            target = f"→ {log['target_id']}" if log['target_id'] else ""
            
            header += f"│  {action_emoji} {log['action']:<10} {target}\n"
            header += f"│     {time_str}\n"
            
            # Show details if short enough
            if log['details'] and len(log['details']) < 40:
                header += f"│     {log['details'][:37]}...\n"
            
            header += "│\n"
        
        header += "└────────────────────────────\n"
    else:
        header += "\n📭 No audit logs yet\n"
    
    header += "\n💡 Use /auditlog <limit> to see more\n"
    header += get_footer()
    
    await message.answer(header)


@router.message(Command("cachestats"))
async def cmd_cache_stats(message: Message):
    """Handle /cachestats command (Owner only) - View cache statistics."""
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
    
    from cache_manager import get_cache_stats
    
    # Get cache statistics
    stats = await get_cache_stats()
    
    # Calculate cache hit rate (if we have the data)
    total = stats.get('total_entries', 0)
    active = stats.get('active_entries', 0)
    expired = stats.get('expired_entries', 0)
    
    # Format timestamps
    oldest = stats.get('oldest_entry', 'N/A')
    newest = stats.get('newest_entry', 'N/A')
    
    if oldest != 'N/A':
        try:
            from datetime import datetime
            oldest_dt = datetime.fromisoformat(oldest)
            oldest = oldest_dt.strftime("%m/%d %H:%M")
        except:
            pass
    
    if newest != 'N/A':
        try:
            from datetime import datetime
            newest_dt = datetime.fromisoformat(newest)
            newest = newest_dt.strftime("%m/%d %H:%M")
        except:
            pass
    
    stats_msg = (
        "╭───────────────────────────╮\n"
        "│   📊  CACHE STATISTICS    │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "┌─ CACHE STATUS ───────────\n"
        "│\n"
        f"│  Total Entries   ›  {total}\n"
        f"│  Active          ›  {active}\n"
        f"│  Expired         ›  {expired}\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ TIMESTAMPS ─────────────\n"
        "│\n"
        f"│  Oldest Entry    ›  {oldest}\n"
        f"│  Newest Entry    ›  {newest}\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "💡 TTL: 1 hour per entry\n"
        "💡 Use /clearcache to remove expired\n"
        + get_footer()
    )
    
    await message.answer(stats_msg)


@router.message(Command("cbstats"))
async def cmd_cb_stats(message: Message):
    """Handle /cbstats command (Owner only) - View circuit breaker states."""
    if not is_owner(message.from_user.id):
        await message.answer(
            "╭───────────────────────────╮\n"
            "│   🔒  ACCESS DENIED       │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "This command is owner-only."
            + get_footer()
        )
        return

    from gateway_checker import get_circuit_breaker_stats

    stats = await get_circuit_breaker_stats()

    if not stats:
        await message.answer(
            "╭───────────────────────────╮\n"
            "│   ⚡  CIRCUIT BREAKERS    │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "✅ All circuits CLOSED\n"
            "\n"
            "No domains have tripped the\n"
            "circuit breaker yet."
            + get_footer()
        )
        return

    # State emoji mapping
    state_emoji = {
        "closed": "🟢",
        "open": "🔴",
        "half_open": "🟡",
    }

    header = (
        "╭───────────────────────────╮\n"
        "│   ⚡  CIRCUIT BREAKERS    │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Tracking {len(stats)} domain(s)\n"
        "\n"
        "┌─ DOMAIN STATUS ───────────\n"
        "│\n"
    )

    body = ""
    for domain, info in sorted(stats.items(), key=lambda x: x[1]["state"]):
        emoji = state_emoji.get(info["state"], "⚪")
        state_label = info["state"].upper().replace("_", " ")
        failures = info["consecutive_failures"]
        cooldown = info["cooldown_remaining"]

        body += f"│  {emoji} {domain[:25]}\n"
        body += f"│     State    › {state_label}\n"
        body += f"│     Failures › {failures}\n"
        if cooldown > 0:
            body += f"│     Cooldown › {cooldown}s remaining\n"
        body += "│\n"

    footer_block = (
        "└────────────────────────────\n"
        "\n"
        "💡 Use /cbreset <domain> to manually\n"
        "   clear a tripped circuit."
        + get_footer()
    )

    await message.answer(header + body + footer_block)


@router.message(Command("cbreset"))
async def cmd_cb_reset(message: Message):
    """Handle /cbreset <domain> command (Owner only) - Manually reset a circuit breaker."""
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: /cbreset <domain>\n"
            "Example: /cbreset example.com\n\n"
            "Use /cbstats to see tripped domains."
        )
        return

    target = parts[1].strip()
    # Normalise: strip any scheme so we just use the netloc
    from urllib.parse import urlparse
    parsed = urlparse(target if "://" in target else f"https://{target}")
    domain = parsed.netloc.lower() or target.lower()

    from gateway_checker import _circuit_breaker
    await _circuit_breaker.reset(f"https://{domain}/")

    logger.info(f"Owner {message.from_user.id} manually reset circuit for {domain}")
    await message.answer(
        "╭───────────────────────────╮\n"
        "│   ✅  CIRCUIT RESET       │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Circuit for {domain} has been\n"
        "reset to CLOSED state.\n"
        "\n"
        "Next request to this domain\n"
        "will go through normally."
        + get_footer()
    )


@router.message(Command("clearcache"))
async def cmd_clear_cache(message: Message):
    """Handle /clearcache command (Owner only) - Clear expired cache entries."""
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
    
    from cache_manager import clear_expired_cache
    
    # Show processing message
    processing_msg = await message.answer(
        "╭───────────────────────────╮\n"
        "│   🧹  CLEARING CACHE      │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Removing expired entries..."
    )
    
    # Clear expired cache
    deleted = await clear_expired_cache()
    
    # Delete processing message
    try:
        await processing_msg.delete()
    except:
        pass
    
    # Send result
    result_msg = (
        "╭───────────────────────────╮\n"
        "│   ✅  CACHE CLEARED       │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Removed {deleted} expired entries\n"
        "\n"
        "💡 Use /cachestats to view stats"
        + get_footer()
    )
    
    await message.answer(result_msg)


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    """Handle /buy command showing subscription plans with buttons."""

    buy_message = (
        "╭───────────────────────────╮\n"
        "│   💎  PREMIUM ACCESS      │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Get unlimited access to\n"
        "Gateway Hunter!\n"
        "\n"
        "┌─ FEATURES ────────────────\n"
        "│\n"
        "│  ✓  400+ Payment Gateways\n"
        "│  ✓  Unlimited Scans\n"
        "│  ✓  Security Detection\n"
        "│  ✓  Priority Support\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "💡 Select a plan below:"
        + get_footer()
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 Month - $20", callback_data="plan_1m"),
            InlineKeyboardButton(text="3 Months - $50", callback_data="plan_3m")
        ],
        [
            InlineKeyboardButton(text="6 Months - $90", callback_data="plan_6m"),
            InlineKeyboardButton(text="1 Year - $150 🔥", callback_data="plan_1y")
        ],
        [InlineKeyboardButton(text="💳 Payment Info", callback_data="payment_info")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
    ])

    await message.answer(buy_message, reply_markup=keyboard)


@router.message(Command("subscription"))
async def cmd_subscription(message: Message):
    """Check subscription status with buttons."""
    user_id = message.from_user.id

    if is_owner(user_id):
        keyboard = get_back_to_menu_keyboard()
        await message.answer(
            "╭───────────────────────────╮\n"
            "│   👑  OWNER ACCESS        │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You have unlimited lifetime access.\n"
            "You are the system administrator."
            + get_footer(),
            reply_markup=keyboard
        )
        return

    expiry = await async_get_subscription_expiry(user_id)

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

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏱️ Extend Plan", callback_data="subscription_plans")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
        ])
    else:
        status_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  NO SUBSCRIPTION     │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You do not have an active plan.\n"
            "\n"
            "Click below to view plans and upgrade!"
            + get_footer()
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 View Plans", callback_data="subscription")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
        ])

    await message.answer(status_msg, reply_markup=keyboard)


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

        # Validate duration format
        if not validate_duration(duration):
            await message.answer(
                "❌ Invalid duration format!\n\n"
                "Valid formats:\n"
                "  • 1d, 7d, 30d (days)\n"
                "  • 1w, 2w (weeks)\n"
                "  • 1m, 3m, 6m (months)\n"
                "  • 1y, 2y (years)\n\n"
                "Example: /addsub 123456789 1m"
            )
            return

        new_expiry = await async_add_subscription(target_user_id, duration)

        if new_expiry:
            # Log admin action
            await log_admin_action(
                admin_user_id=message.from_user.id,
                action="addsub",
                target_user_id=target_user_id,
                details=f"Added {duration} subscription, new expiry: {new_expiry}"
            )
            
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



@router.message(Command("history"))
async def cmd_history(message: Message):
    """Handle /history command - view scan history."""
    user_id = message.from_user.id
    
    # Check registration
    if not await async_is_user_registered(user_id):
        await message.answer(
            "⚠️ Please /register first."
            + get_footer()
        )
        return
    
    # Import the pagination function
    from database import get_user_scan_history_paginated
    
    # Get history with pagination (page 1, 5 per page)
    history, total = await get_user_scan_history_paginated(user_id, page=1, per_page=5)
    
    if not history:
        await message.answer(
            "╭───────────────────────────╮\n"
            "│   📭  NO HISTORY          │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You haven't scanned any URLs yet.\n"
            "\n"
            "Use /url <link> to scan a website!"
            + get_footer()
        )
        return
    
    # Format response
    response = (
        "╭───────────────────────────╮\n"
        "│   📋  SCAN HISTORY        │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Total Scans: {total}\n"
        f"Page: 1 of {(total + 4) // 5}\n"
        "\n"
    )
    
    for i, scan in enumerate(history, 1):
        # Format URL (truncate if too long)
        url_display = scan['url'][:35] + "..." if len(scan['url']) > 35 else scan['url']
        
        # Format date
        try:
            scan_date = datetime.fromisoformat(scan['scanned_at'])
            date_str = scan_date.strftime("%m/%d %H:%M")
        except:
            date_str = "N/A"
        
        # Format gateways (show first 3)
        gateways = scan.get('gateways', [])
        if gateways:
            gateway_str = ", ".join(gateways[:3])
            if len(gateways) > 3:
                gateway_str += f" +{len(gateways) - 3}"
        else:
            gateway_str = "None"
        
        response += f"{i}. {url_display}\n"
        response += f"   📅 {date_str}\n"
        response += f"   💳 {gateway_str}\n\n"
    
    # Add pagination buttons if needed
    total_pages = (total + 4) // 5
    
    keyboard_buttons = []
    
    if total_pages > 1:
        nav_buttons = [InlineKeyboardButton(text="▶️ Next", callback_data="history_page_2")]
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Menu", callback_data="back_main")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(response + get_footer(), reply_markup=keyboard)


@router.message(Command("export"))
async def cmd_export(message: Message):
    """Handle /export command — offer CSV, JSON, and TXT download options."""
    user_id = message.from_user.id

    if not await async_is_user_registered(user_id):
        await message.answer(
            "⚠️ Please /register first."
            + get_footer()
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 CSV",  callback_data="export_csv"),
            InlineKeyboardButton(text="📋 JSON", callback_data="export_json"),
            InlineKeyboardButton(text="📄 TXT",  callback_data="export_txt"),
        ],
        [InlineKeyboardButton(text="🏠 Back", callback_data="back_main")],
    ])

    await message.answer(
        "╭───────────────────────────╮\n"
        "│   📤  EXPORT SCAN HISTORY │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Choose a format to download\n"
        "your scan results:\n"
        "\n"
        "┌─ FORMATS ─────────────────\n"
        "│\n"
        "│  📊  CSV  — spreadsheet\n"
        "│  📋  JSON — structured data\n"
        "│  📄  TXT  — plain text\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "Up to 1 000 most recent scans."
        + get_footer(),
        reply_markup=keyboard,
    )


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

async def _get_export_data(user_id: int) -> list:
    """Fetch full scan history for export."""
    from database import get_user_scan_history_all
    return await get_user_scan_history_all(user_id)


def _build_csv(rows: list) -> bytes:
    """Build a UTF-8 CSV file from scan rows."""
    import csv
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "url", "scanned_at", "status_code", "gateways",
        "security_type", "cvv_status", "cloudflare", "captcha",
        "inbuilt_payment", "ecommerce_platform", "cart_abandonment",
    ])
    writer.writeheader()
    for r in rows:
        writer.writerow({
            **r,
            "gateways": ", ".join(r["gateways"]) if r["gateways"] else "None",
        })
    return output.getvalue().encode("utf-8")


def _build_json(rows: list) -> bytes:
    """Build a pretty-printed JSON file from scan rows."""
    import json
    return json.dumps(rows, indent=2, ensure_ascii=False).encode("utf-8")


def _build_txt(rows: list) -> bytes:
    """Build a human-readable TXT report from scan rows."""
    lines = [
        "╔══════════════════════════════════════╗",
        "║      GATEWAY HUNTER — SCAN EXPORT    ║",
        f"║  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}             ║",
        f"║  Total scans: {len(rows):<23}║",
        "╚══════════════════════════════════════╝",
        "",
    ]
    for i, r in enumerate(rows, 1):
        # Format timestamp
        try:
            dt = datetime.fromisoformat(r["scanned_at"])
            ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            ts = r["scanned_at"]

        gateways_str = ", ".join(r["gateways"]) if r["gateways"] else "None detected"
        cf_str  = "Yes" if r["cloudflare"]       else "No"
        cap_str = "Yes" if r["captcha"]           else "No"
        inb_str = "Yes" if r["inbuilt_payment"]   else "No"

        lines += [
            f"┌─ SCAN #{i} ─────────────────────────────",
            f"│  URL       : {r['url']}",
            f"│  Scanned   : {ts}",
            f"│  Status    : HTTP {r['status_code']}",
            f"│  Gateways  : {gateways_str}",
            f"│  Security  : {r['security_type']}",
            f"│  CVV       : {r['cvv_status']}",
            f"│  Cloudflare: {cf_str}",
            f"│  Captcha   : {cap_str}",
            f"│  Inbuilt   : {inb_str}",
            f"│  Platform  : {r['ecommerce_platform']}",
            f"│  Cart Tool : {r['cart_abandonment']}",
            "└────────────────────────────────────────",
            "",
        ]

    return "\n".join(lines).encode("utf-8")


async def _send_export_file(
    callback: CallbackQuery,
    fmt: str,
    data: bytes,
    filename: str,
    mime: str,
    record_count: int = 0,
) -> None:
    """Send the export file to the user as a document."""
    from aiogram.types import BufferedInputFile

    await callback.answer()
    processing = await callback.message.answer(
        "⏳ Generating your export file..."
    )

    file = BufferedInputFile(data, filename=filename)
    caption = (
        f"📤 Your scan history export ({fmt.upper()})\n"
        f"Records: {record_count}\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    try:
        await callback.message.answer_document(file, caption=caption)
    finally:
        try:
            await processing.delete()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Export callback handlers
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "export_csv")
async def callback_export_csv(callback: CallbackQuery):
    """Export scan history as CSV."""
    user_id = callback.from_user.id
    rows = await _get_export_data(user_id)

    if not rows:
        await callback.answer("📭 No scan history to export.", show_alert=True)
        return

    data = _build_csv(rows)
    filename = f"gateway_scans_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    await _send_export_file(callback, "CSV", data, filename, "text/csv", record_count=len(rows))


@router.callback_query(F.data == "export_json")
async def callback_export_json(callback: CallbackQuery):
    """Export scan history as JSON."""
    user_id = callback.from_user.id
    rows = await _get_export_data(user_id)

    if not rows:
        await callback.answer("📭 No scan history to export.", show_alert=True)
        return

    data = _build_json(rows)
    filename = f"gateway_scans_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    await _send_export_file(callback, "JSON", data, filename, "application/json", record_count=len(rows))


@router.callback_query(F.data == "export_txt")
async def callback_export_txt(callback: CallbackQuery):
    """Export scan history as plain text report."""
    user_id = callback.from_user.id
    rows = await _get_export_data(user_id)

    if not rows:
        await callback.answer("📭 No scan history to export.", show_alert=True)
        return

    data = _build_txt(rows)
    filename = f"gateway_scans_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    await _send_export_file(callback, "TXT", data, filename, "text/plain", record_count=len(rows))


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

    # Sanitize broadcast message text
    broadcast_text = sanitize_text_input(message.text, max_length=4000)

    # Send broadcast to all users
    user_ids = await async_get_all_user_ids()
    stats = {'sent': 0, 'failed': 0}

    logger.info(f"Broadcasting message to {len(user_ids)} users")

    for user_id in user_ids:
        try:
            await bot.send_message(user_id, broadcast_text)
            stats['sent'] += 1
        except Exception as e:
            logger.error(f"Failed to send message to {user_id}: {str(e)}")
            stats['failed'] += 1

    logger.info(f"Broadcast complete - Sent: {stats['sent']}, Failed: {stats['failed']}")

    # Log admin action
    await log_admin_action(
        admin_user_id=message.from_user.id,
        action="broadcast",
        details=f"Sent to {stats['sent']} users, {stats['failed']} failed"
    )

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
# CALLBACK QUERY HANDLERS - Interactive Buttons
# =============================================================================

@router.callback_query(F.data == "back_main")
async def callback_back_main(callback: CallbackQuery):
    """Handle back to main menu button."""
    await callback.answer()

    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "User"

    welcome_message = (
        "╭───────────────────────────╮\n"
        "│   🎯  GATEWAY HUNTER      │\n"
        "│   Payment Gateway Scanner │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Hey {first_name}! 👋\n"
        "\n"
        "💡 Choose an action below:"
        + get_footer()
    )

    keyboard = get_owner_menu_keyboard() if is_owner(user_id) else get_main_menu_keyboard()

    await callback.message.edit_text(welcome_message, reply_markup=keyboard)


@router.callback_query(F.data == "scan_url")
async def callback_scan_url(callback: CallbackQuery, state: FSMContext):
    """Handle scan URL button press."""
    await callback.answer()

    user_id = callback.from_user.id

    # Check if user is registered
    if not await async_is_user_registered(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Register Now", callback_data="register")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")]
        ])

        await callback.message.edit_text(
            "╭───────────────────────────╮\n"
            "│   ⚠️  ACCESS REQUIRED     │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You need to register first!\n"
            "\n"
            "Click 'Register Now' to get access."
            + get_footer(),
            reply_markup=keyboard
        )
        return

    # Check subscription
    if not await async_check_subscription(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 View Plans", callback_data="subscription")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")]
        ])

        await callback.message.edit_text(
            "╭───────────────────────────╮\n"
            "│   💳  SUBSCRIPTION NEEDED │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You need an active subscription\n"
            "to use the scanner.\n"
            "\n"
            "Click 'View Plans' to see options."
            + get_footer(),
            reply_markup=keyboard
        )
        return

    # Prompt for URL
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="back_main")]
    ])

    await callback.message.edit_text(
        "🔍 **URL SCANNER**\n"
        "───────────────────\n\n"
        "📥 Send me the URL to scan\n\n"
        "**Examples:**\n"
        "• `example.com`\n"
        "• `https://site.com/checkout`\n"
        "• Multiple URLs (space-separated)\n\n"
        "💡 Use /url command for direct scanning",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

    await state.set_state(ScanState.waiting_for_url)


@router.message(ScanState.waiting_for_url, F.text)
async def handle_scan_url_input(message: Message, state: FSMContext):
    """Handle URL input during scan flow."""
    await state.clear()

    user_id = message.from_user.id

    # Parse URLs from message
    raw_urls = [url.strip() for url in message.text.split() if url.strip()]

    if not raw_urls:
        await message.answer("❌ No valid URLs provided. Use /start to try again.")
        return

    # Sanitize and normalize URLs
    urls = []
    for raw_url in raw_urls:
        normalized = normalize_url(raw_url)
        sanitized, is_safe = sanitize_url(normalized)
        if not is_safe:
            await message.answer(
                "⚠️ Suspicious URL detected and blocked:\n\n"
                f"{raw_url[:50]}...\n\n"
                "Please provide a valid HTTP(S) URL."
                + get_footer()
            )
            continue
        urls.append(sanitized)
    
    if not urls:
        await message.answer(
            "❌ All provided URLs were blocked for security reasons.\n\n"
            "Please provide valid HTTP(S) URLs."
            + get_footer()
        )
        return

    if len(urls) > Config.MAX_URLS_PER_REQUEST:
        await message.answer(
            f"❌ Too many URLs!\n\n"
            f"Limit: {Config.MAX_URLS_PER_REQUEST} URLs\n"
            f"Sent: {len(urls)} URLs\n\n"
            "Please split into smaller batches."
            + get_footer()
        )
        return

    # Process URLs (reuse existing logic)
    url_word = "URL" if len(urls) == 1 else "URLs"
    processing_msg = await message.answer(
        "╭───────────────────────────╮\n"
        "│   ⏳  SCANNING            │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Analyzing {len(urls)} {url_word}..."
    )

    try:
        results = await process_urls_async(urls, user_id)
    except Exception as e:
        logger.error(f"Error in async processing: {str(e)}")
        results = [f"❌ Error: {str(e)[:100]}"]

    try:
        await processing_msg.delete()
    except:
        pass

    # Save URLs to state for rescan functionality
    await state.update_data(last_urls=urls)

    # Send results with action buttons
    for i, result in enumerate(results):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Rescan", callback_data=f"rescan_{i}"),
                InlineKeyboardButton(text="🏠 Menu", callback_data="back_main")
            ]
        ])
        await message.answer(result + get_footer(), reply_markup=keyboard)


@router.callback_query(F.data == "register")
async def callback_register(callback: CallbackQuery):
    """Handle register button press."""
    await callback.answer()

    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "User"

    status = await async_register_user(user_id, callback.from_user.username, first_name)

    if status == 'new':
        logger.info(f"User {user_id} registered via button")
        keyboard = get_main_menu_keyboard()

        await callback.message.edit_text(
            "╭───────────────────────────╮\n"
            "│   ✅  ACCESS GRANTED      │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"Welcome aboard, {first_name}! 🎉\n"
            "\n"
            "You now have full access to\n"
            "Gateway Hunter.\n"
            "\n"
            "🚀 Click 'Scan Website' to begin!"
            + get_footer(),
            reply_markup=keyboard
        )
    else:
        keyboard = get_main_menu_keyboard()
        await callback.message.edit_text(
            "╭───────────────────────────╮\n"
            "│   ℹ️  ALREADY REGISTERED  │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"Hey {first_name}, you're all set! 👋\n"
            "\n"
            "Your account is active."
            + get_footer(),
            reply_markup=keyboard
        )


@router.callback_query(F.data == "subscription")
async def callback_subscription(callback: CallbackQuery):
    """Show subscription plans with inline buttons."""
    await callback.answer()

    user_id = callback.from_user.id

    # Check if owner
    if is_owner(user_id):
        keyboard = get_back_to_menu_keyboard()
        await callback.message.edit_text(
            "╭───────────────────────────╮\n"
            "│   👑  OWNER ACCESS        │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You have unlimited lifetime access.\n"
            "You are the system administrator."
            + get_footer(),
            reply_markup=keyboard
        )
        return

    # Check current subscription
    expiry = await async_get_subscription_expiry(user_id)

    if expiry and expiry > datetime.now():
        time_left = expiry - datetime.now()
        days_left = time_left.days
        hours_left = time_left.seconds // 3600

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏱️ Extend Plan", callback_data="subscription_plans")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")]
        ])

        await callback.message.edit_text(
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
            + get_footer(),
            reply_markup=keyboard
        )
    else:
        # Show plans
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="1 Month - $20", callback_data="plan_1m"),
                InlineKeyboardButton(text="3 Months - $50", callback_data="plan_3m")
            ],
            [
                InlineKeyboardButton(text="6 Months - $90", callback_data="plan_6m"),
                InlineKeyboardButton(text="1 Year - $150 🔥", callback_data="plan_1y")
            ],
            [InlineKeyboardButton(text="💳 Payment Info", callback_data="payment_info")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")]
        ])

        await callback.message.edit_text(
            "╭───────────────────────────╮\n"
            "│   💎  PREMIUM ACCESS      │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Get unlimited access to\n"
            "Gateway Hunter!\n"
            "\n"
            "┌─ FEATURES ────────────────\n"
            "│\n"
            "│  ✓  400+ Payment Gateways\n"
            "│  ✓  Unlimited Scans\n"
            "│  ✓  Security Detection\n"
            "│  ✓  Priority Support\n"
            "│\n"
            "└────────────────────────────\n"
            "\n"
            "💡 Select a plan below:"
            + get_footer(),
            reply_markup=keyboard
        )


@router.callback_query(F.data.startswith("plan_"))
async def callback_plan_select(callback: CallbackQuery):
    """Show payment options for selected plan."""
    await callback.answer()

    plan_id = callback.data.split("_")[1]
    plan_info = Config.SUBSCRIPTION_PLANS.get(plan_id)

    if not plan_info:
        await callback.answer("❌ Invalid plan", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₿ Bitcoin (BTC)", callback_data=f"pay_btc_{plan_id}")],
        [InlineKeyboardButton(text="🪙 Litecoin (LTC)", callback_data=f"pay_ltc_{plan_id}")],
        [InlineKeyboardButton(text="💵 USDT (TRC20)", callback_data=f"pay_usdt_{plan_id}")],
        [InlineKeyboardButton(text="⬅️ Back to Plans", callback_data="subscription")]
    ])

    await callback.message.edit_text(
        f"💎 **{plan_info['name']} Plan**\n"
        f"Price: **{plan_info['price']}**\n"
        "───────────────────────\n\n"
        "Choose your payment method:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("pay_"))
async def callback_payment_method(callback: CallbackQuery):
    """Show payment address for selected method."""
    await callback.answer()

    parts = callback.data.split("_")
    crypto = parts[1]  # btc, ltc, usdt
    plan_id = parts[2]  # 1m, 3m, etc.

    plan_info = Config.SUBSCRIPTION_PLANS.get(plan_id)

    # Get crypto address
    addresses = {
        "btc": ("Bitcoin (BTC)", Config.BTC_ADDRESS),
        "ltc": ("Litecoin (LTC)", Config.LTC_ADDRESS),
        "usdt": ("USDT TRC20", Config.USDT_TRC20_ADDRESS)
    }

    crypto_name, address = addresses.get(crypto, ("Unknown", "N/A"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Payment Sent", url=f"https://t.me/{Config.CONTACT_USERNAME}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data=f"plan_{plan_id}")]
    ])

    await callback.message.edit_text(
        f"💎 **{plan_info['name']} - {plan_info['price']}**\n"
        f"Payment: **{crypto_name}**\n"
        "───────────────────────\n\n"
        "📋 **Payment Address:**\n"
        f"`{address}`\n\n"
        "**Next Steps:**\n"
        "1️⃣ Send payment to address above\n"
        "2️⃣ Take screenshot of transaction\n"
        "3️⃣ Click 'Payment Sent' to contact owner\n"
        "4️⃣ Wait for activation (usually <1 hour)\n\n"
        "💡 Tap address to copy",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "payment_info")
async def callback_payment_info(callback: CallbackQuery):
    """Show all payment addresses."""
    await callback.answer()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Plans", callback_data="subscription")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   💳  PAYMENT METHODS     │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "**Bitcoin (BTC)**\n"
        f"`{Config.BTC_ADDRESS}`\n\n"
        "**Litecoin (LTC)**\n"
        f"`{Config.LTC_ADDRESS}`\n\n"
        "**USDT (TRC20)**\n"
        f"`{Config.USDT_TRC20_ADDRESS}`\n\n"
        "💡 Tap to copy address\n"
        "\n"
        "After payment, contact:\n"
        f"👤 @{Config.CONTACT_USERNAME}"
        + get_footer(),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("history_page_"))
async def callback_history_page(callback: CallbackQuery):
    """Handle history pagination."""
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Extract page number from callback data
    try:
        page = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        page = 1
    
    # Import the pagination function
    from database import get_user_scan_history_paginated
    
    # Get history for the requested page
    history, total = await get_user_scan_history_paginated(user_id, page=page, per_page=5)
    
    if not history:
        await callback.answer("No history found", show_alert=True)
        return
    
    # Format response
    total_pages = (total + 4) // 5
    
    response = (
        "╭───────────────────────────╮\n"
        "│   📋  SCAN HISTORY        │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Total Scans: {total}\n"
        f"Page: {page} of {total_pages}\n"
        "\n"
    )
    
    for i, scan in enumerate(history, 1):
        # Calculate global index
        global_index = (page - 1) * 5 + i
        
        # Format URL (truncate if too long)
        url_display = scan['url'][:35] + "..." if len(scan['url']) > 35 else scan['url']
        
        # Format date
        try:
            scan_date = datetime.fromisoformat(scan['scanned_at'])
            date_str = scan_date.strftime("%m/%d %H:%M")
        except:
            date_str = "N/A"
        
        # Format gateways (show first 3)
        gateways = scan.get('gateways', [])
        if gateways:
            gateway_str = ", ".join(gateways[:3])
            if len(gateways) > 3:
                gateway_str += f" +{len(gateways) - 3}"
        else:
            gateway_str = "None"
        
        response += f"{global_index}. {url_display}\n"
        response += f"   📅 {date_str}\n"
        response += f"   💳 {gateway_str}\n\n"
    
    # Add pagination buttons
    keyboard_buttons = []
    
    if total_pages > 1:
        nav_buttons = []
        
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"history_page_{page-1}"))
        
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="▶️ Next", callback_data=f"history_page_{page+1}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Menu", callback_data="back_main")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(response + get_footer(), reply_markup=keyboard)


@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Show help menu with categories."""
    await callback.answer()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Getting Started", callback_data="help_start")],
        [InlineKeyboardButton(text="🔍 How to Scan", callback_data="help_scan")],
        [InlineKeyboardButton(text="💳 Payment Gateways", callback_data="help_gateways")],
        [InlineKeyboardButton(text="🔐 Security Features", callback_data="help_security")],
        [InlineKeyboardButton(text="💬 Contact Support", url=f"https://t.me/{Config.CONTACT_USERNAME}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   📖  HELP CENTER         │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Choose a topic to learn more:\n"
        "\n"
        "💡 You can also use these commands:\n"
        "• /help - Full text guide\n"
        "• /url <link> - Quick scan"
        + get_footer(),
        reply_markup=keyboard
    )


@router.callback_query(F.data == "help_start")
async def callback_help_start(callback: CallbackQuery):
    """Show getting started help."""
    await callback.answer()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Help", callback_data="help")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   🚀  GETTING STARTED     │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "**Step 1:** Register\n"
        "Use /register command or click\n"
        "'Register Now' button\n"
        "\n"
        "**Step 2:** Subscribe\n"
        "Choose a plan with /buy or\n"
        "click 'Subscribe' button\n"
        "\n"
        "**Step 3:** Start Scanning\n"
        "Use /url <link> or click\n"
        "'Scan Website' button\n"
        "\n"
        "**Step 4:** Get Results\n"
        "Instant analysis of payment\n"
        "gateways and security!"
        + get_footer(),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "help_scan")
async def callback_help_scan(callback: CallbackQuery):
    """Show scanning help."""
    await callback.answer()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Help", callback_data="help")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   🔍  HOW TO SCAN         │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "**URL Formats:**\n"
        "✓ example.com\n"
        "✓ www.site.com\n"
        "✓ https://site.com\n"
        "✓ https://site.com/checkout\n"
        "\n"
        "**Multiple URLs:**\n"
        "/url site1.com site2.com\n"
        "\n"
        "**Pro Tips:**\n"
        "• Target checkout pages\n"
        "• No protocol needed\n"
        f"• Max {Config.MAX_URLS_PER_REQUEST} URLs per scan\n"
        "• Real-time progress with ETA\n"
        "• Use 🔄 Quick Rescan button to rescan\n"
        "\n"
        "**What We Detect:**\n"
        "💳 400+ Payment Gateways\n"
        "🔐 Security Features\n"
        "🛡️ Protection Systems\n"
        "🛒 E-commerce Platforms\n"
        "🛡️ Cart Abandonment Tools"
        + get_footer(),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "help_gateways")
async def callback_help_gateways(callback: CallbackQuery):
    """Show payment gateways info."""
    await callback.answer()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Help", callback_data="help")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   💳  PAYMENT GATEWAYS    │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "**Detection Database:**\n"
        "🌍 400+ Gateway Signatures\n"
        "\n"
        "**Categories:**\n"
        "• Global Major (Stripe, PayPal)\n"
        "• European (Mollie, Klarna)\n"
        "• Asia-Pacific (Razorpay, Alipay)\n"
        "• Middle East & Africa\n"
        "• Latin America\n"
        "• Cryptocurrency (BitPay, Coinbase)\n"
        "• Buy Now Pay Later (Afterpay)\n"
        "\n"
        "**Confidence Levels:**\n"
        "🟢 High - SDK/API detected\n"
        "🟡 Medium - Form/iframe found\n"
        "🔵 Low - Keyword match"
        + get_footer(),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "help_security")
async def callback_help_security(callback: CallbackQuery):
    """Show security features info."""
    await callback.answer()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Help", callback_data="help")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   🔐  SECURITY DETECTION  │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "**What We Check:**\n"
        "\n"
        "🔐 **3D Secure**\n"
        "Verified by Visa (VbV)\n"
        "Mastercard SecureCode (MSC)\n"
        "\n"
        "📱 **OTP Verification**\n"
        "SMS/Email verification\n"
        "\n"
        "🔢 **CVV/CVC Requirements**\n"
        "Card security code checks\n"
        "\n"
        "🛡️ **Protection Systems**\n"
        "• Cloudflare\n"
        "• Captcha (reCAPTCHA, hCaptcha)\n"
        "• WAF (Web Application Firewall)\n"
        "\n"
        "📦 **Checkout Types**\n"
        "Hosted, Embedded, or Inbuilt"
        + get_footer(),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "about")
async def callback_about(callback: CallbackQuery):
    """Show about information."""
    await callback.answer()

    keyboard = get_back_to_menu_keyboard()

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   ℹ️  ABOUT               │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "**Gateway Hunter**\n"
        "Payment Gateway Scanner Bot\n"
        "\n"
        "**Version:** 2.0\n"
        "**Framework:** aiogram 3.x\n"
        "**Database:** 400+ Gateways\n"
        "\n"
        "**Features:**\n"
        "✓ Multi-tier detection\n"
        "✓ Security analysis\n"
        "✓ Cloudflare detection\n"
        "✓ Batch processing\n"
        "✓ Real-time results\n"
        "\n"
        f"**Creator:** @{Config.CONTACT_USERNAME}\n"
        f"**Bot:** @{Config.BOT_USERNAME}\n"
        "\n"
        "🌟 Built with ❤️ for security researchers"
        + get_footer(),
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "stats")
async def callback_stats(callback: CallbackQuery):
    """Show bot statistics (owner only)."""
    if not is_owner(callback.from_user.id):
        await callback.answer("⚠️ Owner only!", show_alert=True)
        return

    await callback.answer()

    user_count = await async_get_user_count()
    rate_status = "✅ Enabled" if Config.ENABLE_RATE_LIMITING else "❌ Disabled"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="broadcast_start")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_main")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   📊  BOT STATISTICS      │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "┌─ USER BASE ───────────────\n"
        "│\n"
        f"│  Total Users  ›  {user_count}\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "┌─ CONFIGURATION ───────────\n"
        "│\n"
        f"│  Bot        ›  @{Config.BOT_USERNAME}\n"
        f"│  Rate Limit ›  {rate_status}\n"
        f"│  Max URLs   ›  {Config.MAX_URLS_PER_REQUEST}/request\n"
        "│\n"
        "└────────────────────────────\n"
        "\n"
        "✨ System running smoothly"
        + get_footer(),
        reply_markup=keyboard
    )


@router.callback_query(F.data == "broadcast_start")
async def callback_broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Start broadcast flow (owner only)."""
    if not is_owner(callback.from_user.id):
        await callback.answer("⚠️ Owner only!", show_alert=True)
        return

    await callback.answer()

    # Enter broadcast state
    await state.set_state(BroadcastState.waiting_for_message)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="back_main")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   📢  BROADCAST MODE      │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Send your message now.\n"
        "\n"
        "It will be delivered to all users.\n"
        "\n"
        "Click Cancel to abort."
        + get_footer(),
        reply_markup=keyboard
    )


@router.callback_query(F.data == "subscription_plans")
async def callback_subscription_plans(callback: CallbackQuery):
    """Show subscription plans for extension."""
    await callback.answer()

    # Show plans (same as subscription but for extension)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 Month - $20", callback_data="plan_1m"),
            InlineKeyboardButton(text="3 Months - $50", callback_data="plan_3m")
        ],
        [
            InlineKeyboardButton(text="6 Months - $90", callback_data="plan_6m"),
            InlineKeyboardButton(text="1 Year - $150 🔥", callback_data="plan_1y")
        ],
        [InlineKeyboardButton(text="💳 Payment Info", callback_data="payment_info")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="subscription")]
    ])

    await callback.message.edit_text(
        "╭───────────────────────────╮\n"
        "│   ⏱️  EXTEND SUBSCRIPTION │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Choose how long to extend\n"
        "your subscription:\n"
        "\n"
        "💡 Time will be added to your\n"
        "current expiry date."
        + get_footer(),
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("rescan_"))
async def callback_rescan(callback: CallbackQuery, state: FSMContext):
    """Handle rescan button - rescan the last URLs."""
    await callback.answer("Rescanning...")
    
    # Get stored URLs from state
    data = await state.get_data()
    urls = data.get('last_urls', [])
    
    if not urls:
        await callback.message.answer(
            "╭───────────────────────────╮\n"
            "│   ℹ️  NO RECENT SCANS     │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Use /url <link> to scan a URL."
            + get_footer()
        )
        return
    
    # Extract index from callback data
    try:
        index = int(callback.data.split("_")[1])
        if 0 <= index < len(urls):
            url_to_rescan = [urls[index]]
        else:
            url_to_rescan = urls
    except (IndexError, ValueError):
        url_to_rescan = urls
    
    # Process the rescan
    user_id = callback.from_user.id
    processing_msg = await callback.message.answer(
        "╭───────────────────────────╮\n"
        "│   🔄 RESCANNING           │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Please wait..."
    )
    
    try:
        results = await process_urls_async(url_to_rescan, user_id, processing_msg)
    except Exception as e:
        logger.error(f"Error in rescan: {str(e)}")
        results = [f"❌ Error: {str(e)[:100]}"]
    
    try:
        await processing_msg.delete()
    except:
        pass
    
    # Send results with action buttons
    footer = get_footer()
    for i, result in enumerate(results):
        msg_text = result.rstrip() + footer
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Rescan", callback_data=f"rescan_{i}"),
                InlineKeyboardButton(text="🏠 Menu", callback_data="back_main")
            ]
        ])
        await callback.message.answer(msg_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("quick_rescan_"))
async def callback_quick_rescan(callback: CallbackQuery, state: FSMContext):
    """Handle Quick Rescan button - rescan a specific URL from results."""
    await callback.answer("🔄 Rescanning...")
    
    # Get stored URLs from state
    data = await state.get_data()
    urls = data.get('last_urls', [])
    
    if not urls:
        await callback.message.answer(
            "╭───────────────────────────╮\n"
            "│   ℹ️  NO RECENT SCANS     │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Use /url <link> to scan a URL."
            + get_footer()
        )
        return
    
    # Extract index from callback data (format: quick_rescan_0, quick_rescan_1, etc.)
    try:
        index = int(callback.data.split("_")[2])
        if 0 <= index < len(urls):
            url_to_rescan = urls[index]
        else:
            await callback.answer("❌ URL not found", show_alert=True)
            return
    except (IndexError, ValueError) as e:
        logger.error(f"Error parsing quick rescan index: {e}")
        await callback.answer("❌ Invalid rescan request", show_alert=True)
        return
    
    # Log the rescan
    user_id = callback.from_user.id
    logger.info(f"User {user_id} quick rescanning URL: {url_to_rescan}")
    
    # Show rescanning message
    processing_msg = await callback.message.answer(
        "╭───────────────────────────╮\n"
        "│   🔄 QUICK RESCAN         │\n"
        "╰───────────────────────────╯\n"
        "\n"
        f"Rescanning URL...\n"
        "\n"
        "Please wait..."
    )
    
    # Process the rescan (single URL)
    try:
        results = await process_urls_async([url_to_rescan], user_id, processing_msg)
    except Exception as e:
        logger.error(f"Error in quick rescan: {str(e)}")
        results = [
            "╭───────────────────────────╮\n"
            "│   ❌  RESCAN FAILED       │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"Error: {str(e)[:100]}\n"
            "\n"
            "Please try again."
        ]
    
    # Delete processing message
    try:
        await processing_msg.delete()
    except:
        pass
    
    # Send result with Quick Rescan button
    footer = get_footer()
    for i, result in enumerate(results):
        msg_text = result.rstrip() + footer
        
        # Add Quick Rescan button for the result
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Quick Rescan", callback_data=f"quick_rescan_{index}")]
        ])
        
        await callback.message.answer(msg_text, reply_markup=keyboard)


# =============================================================================
# URL PROCESSING HANDLER
# =============================================================================

@router.message(Command("url"))
async def cmd_url_check(message: Message, command: CommandObject, state: FSMContext):
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
    if not await async_is_user_registered(user_id):
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
    if not await async_check_subscription(user_id):
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

    # Check rate limit (now async with database persistence)
    if not await rate_limiter.is_allowed(user_id):
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

    # Sanitize and normalize URLs (add https:// if missing)
    urls = []
    for raw_url in raw_urls:
        normalized = normalize_url(raw_url)
        sanitized, is_safe = sanitize_url(normalized)
        if not is_safe:
            await message.answer(
                "╭───────────────────────────╮\n"
                "│   ⚠️  SUSPICIOUS URL      │\n"
                "╰───────────────────────────╯\n"
                "\n"
                "┌─ SECURITY WARNING ────────\n"
                "│\n"
                "│  A potentially dangerous URL\n"
                "│  was detected and blocked.\n"
                "│\n"
                f"│  URL: {raw_url[:30]}...\n"
                "│\n"
                "│  Please check the URL and\n"
                "│  try again with a valid link.\n"
                "│\n"
                "└────────────────────────────"
                + get_footer()
            )
            continue
        urls.append(sanitized)
    
    if not urls:
        await message.answer(
            "╭───────────────────────────╮\n"
            "│   ❌  NO VALID URLs       │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "All provided URLs were blocked\n"
            "for security reasons.\n"
            "\n"
            "Please provide valid HTTP(S) URLs."
            + get_footer()
        )
        return

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
        results = await process_urls_async(urls, user_id, processing_msg)
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
        # Save URLs to state for rescan functionality
        await state.update_data(last_urls=urls)
        
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

        # Send each result as a separate message with Quick Rescan button
        footer = get_footer()
        for i, result in enumerate(results):
            # Combine result with footer
            # result typically ends with newlines, so strip one set of newlines if needed
            msg_text = result.rstrip() + footer
            
            # Add Quick Rescan button for each result
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Quick Rescan", callback_data=f"quick_rescan_{i}")]
            ])
            
            await message.answer(msg_text, reply_markup=keyboard)


async def process_urls_async(
    urls: List[str], 
    user_id: int, 
    progress_message: Optional[Message] = None
) -> List[str]:
    """
    Process all URLs concurrently using persistent HTTP client.
    
    Args:
        urls: List of URLs to check
        user_id: User ID making the request
        progress_message: Optional message to update with progress (for multi-URL scans)
    
    Returns:
        List of formatted result strings
    """
    results = []
    total = len(urls)

    # Get the shared HTTP session from the persistent client
    session = await get_http_session()

    # Create tasks for all URLs
    tasks = []
    for url in urls:
        logger.info(f"User {user_id} checking URL {len(tasks) + 1}/{total}: {url}")
        tasks.append(check_url(url, session))

    # Execute all checks concurrently with progress updates
    if progress_message and total > 2:
        # For multiple URLs, show progress with ETA
        progress = ScanProgress(total_urls=total)
        progress.start()

        completed = 0
        # Create URL-to-index mapping for O(1) lookups (fixes O(n²) bottleneck)
        url_to_idx = {url: i for i, url in enumerate(urls)}
        pending_tasks = {asyncio.create_task(task): url for task, url in zip(tasks, urls)}
        responses = [None] * total  # Preserve order

        while pending_tasks:
            # Wait for next task to complete
            done, pending = await asyncio.wait(
                pending_tasks.keys(),
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in done:
                url = pending_tasks[task]
                idx = url_to_idx[url]  # O(1) dict lookup instead of O(n) list search
                responses[idx] = await task
                del pending_tasks[task]
                completed += 1
                
                # Update progress tracker
                progress.update(current_url=url)
                
                # Update progress message
                try:
                    await progress_message.edit_text(progress.format_status_boxed(include_current=True))
                except Exception as e:
                    logger.debug(f"Could not update progress message: {e}")
                    pass  # Ignore edit errors (e.g., message too old)
    else:
        # For single URL or no progress message, use simple gather
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
                detected_gateways, status_code, captcha, cloudflare, payment_security_type, cvv_cvc_status, inbuilt_status, ecommerce_platform, cart_abandonment = response
                result_line = format_url_result(
                    url, detected_gateways, status_code, captcha,
                    cloudflare, payment_security_type, cvv_cvc_status, inbuilt_status, ecommerce_platform, cart_abandonment
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
# BULK URL SCANNING - File Upload Handler
# =============================================================================

@router.message(Command("bulk"))
async def cmd_bulk_check(message: Message, state: FSMContext):
    """
    Handle /bulk command for batch URL scanning from .txt files.

    User workflow:
    1. Upload a .txt file with URLs (one per line)
    2. Reply to that file with /bulk command
    3. Bot processes all URLs in the file
    """
    user_id = message.from_user.id

    # Check if message is a reply to a document
    if not message.reply_to_message or not message.reply_to_message.document:
        usage_msg = (
            "╭───────────────────────────╮\n"
            "│   ℹ️  BULK SCAN GUIDE     │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Upload URLs in bulk from a file!\n"
            "\n"
            "┌─ HOW TO USE ──────────────\n"
            "│\n"
            "│  1️⃣ Upload a .txt file with\n"
            "│     URLs (one per line)\n"
            "│\n"
            "│  2️⃣ Reply to the file with:\n"
            "│     /bulk\n"
            "│\n"
            "│  3️⃣ Wait for results! ✨\n"
            "│\n"
            "└────────────────────────────\n"
            "\n"
            "┌─ FILE FORMAT ─────────────\n"
            "│\n"
            "│  https://example1.com\n"
            "│  https://example2.com\n"
            "│  example3.com/checkout\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        await message.answer(usage_msg)
        return

    # Check if user is registered
    if not await async_is_user_registered(user_id):
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
    if not await async_check_subscription(user_id):
        payment_required_msg = (
            "╭───────────────────────────╮\n"
            "│   💳  SUBSCRIPTION NEEDED │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "You need an active subscription\n"
            "to use the bulk scanner.\n"
            "\n"
            "Use /buy to see plans and prices."
            + get_footer()
        )
        await message.answer(payment_required_msg)
        await cmd_buy(message)
        return

    # Check rate limit
    if not await rate_limiter.is_allowed(user_id):
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

    # Get document from replied message
    document = message.reply_to_message.document

    # Validate file type
    if not document.file_name.endswith('.txt'):
        invalid_format_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  INVALID FILE TYPE   │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Only .txt files are supported.\n"
            "\n"
            "┌─ REQUIREMENTS ───────────\n"
            "│\n"
            "│  ✓  File format: .txt\n"
            "│  ✓  Max size: 1 MB\n"
            "│  ✓  One URL per line\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )
        await message.answer(invalid_format_msg)
        return

    # Check file size (1 MB limit)
    if document.file_size > 1 * 1024 * 1024:
        file_too_large_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  FILE TOO LARGE      │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"File size: {document.file_size / 1024:.1f} KB\n"
            "Maximum: 1024 KB (1 MB)\n"
            "\n"
            "Please upload a smaller file."
            + get_footer()
        )
        await message.answer(file_too_large_msg)
        return

    # Download and parse file
    try:
        # Send download status
        download_msg = await message.answer(
            "╭───────────────────────────╮\n"
            "│   📥  DOWNLOADING FILE    │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Parsing URLs from file...\n"
            "Please wait..."
        )

        # Download file using bot from message
        file = await message.bot.get_file(document.file_id)
        file_content = await message.bot.download_file(file.file_path)

        # Parse content
        content = file_content.read().decode('utf-8', errors='ignore')

        # Extract URLs (one per line, ignore empty lines and comments)
        raw_urls = []
        for line in content.splitlines():
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                raw_urls.append(line)

        if not raw_urls:
            await download_msg.delete()
            no_urls_msg = (
                "╭───────────────────────────╮\n"
                "│   ❌  NO URLs FOUND       │\n"
                "╰───────────────────────────╯\n"
                "\n"
                "The file appears to be empty\n"
                "or contains no valid URLs.\n"
                "\n"
                "┌─ FILE FORMAT ─────────────\n"
                "│\n"
                "│  https://example1.com\n"
                "│  https://example2.com\n"
                "│  # Comments start with #\n"
                "│\n"
                "└────────────────────────────"
                + get_footer()
            )
            await message.answer(no_urls_msg)
            return

        # Sanitize and normalize URLs
        urls = []
        skipped = 0
        for raw_url in raw_urls:
            normalized = normalize_url(raw_url)
            sanitized, is_safe = sanitize_url(normalized)
            if is_safe:
                urls.append(sanitized)
            else:
                skipped += 1
                logger.warning(f"Skipped suspicious URL in bulk scan: {raw_url[:50]}")

        if not urls:
            await download_msg.delete()
            all_blocked_msg = (
                "╭───────────────────────────╮\n"
                "│   ⚠️  ALL URLs BLOCKED    │\n"
                "╰───────────────────────────╯\n"
                "\n"
                f"Found {len(raw_urls)} URLs in file,\n"
                "but all were blocked for\n"
                "security reasons.\n"
                "\n"
                "Please provide valid HTTP(S) URLs."
                + get_footer()
            )
            await message.answer(all_blocked_msg)
            return

        # Check URL limit
        if len(urls) > Config.MAX_URLS_PER_REQUEST:
            urls = urls[:Config.MAX_URLS_PER_REQUEST]
            await download_msg.delete()
            limited_msg = (
                "╭───────────────────────────╮\n"
                "│   ⚠️  URL LIMIT REACHED   │\n"
                "╰───────────────────────────╯\n"
                "\n"
                f"File contains {len(raw_urls)} URLs.\n"
                f"Processing first {Config.MAX_URLS_PER_REQUEST} URLs.\n"
                "\n"
                "┌─ NOTE ────────────────────\n"
                "│\n"
                "│  For larger batches, split\n"
                "│  into multiple files.\n"
                "│\n"
                "└────────────────────────────\n"
            )
            await message.answer(limited_msg)

        # Update download message to show parsing success
        url_word = "URL" if len(urls) == 1 else "URLs"
        await download_msg.edit_text(
            "╭───────────────────────────╮\n"
            "│   ✅  FILE PARSED         │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"📋 Found: {len(urls)} {url_word}\n"
            f"⚠️ Skipped: {skipped} suspicious\n"
            "\n"
            "Starting scan..."
        )

        # Wait a moment for user to read
        await asyncio.sleep(1)

        # Create processing message
        processing_msg = await message.answer(
            "╭───────────────────────────╮\n"
            "│   ⏳  BULK SCANNING       │\n"
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

        # Delete download message
        try:
            await download_msg.delete()
        except:
            pass

        # Process URLs using existing async function
        logger.info(f"User {user_id} initiated bulk scan of {len(urls)} URLs from file: {document.file_name}")
        results = await process_urls_async(urls, user_id, processing_msg)

        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass

        # Send results
        if results:
            # Save URLs to state for rescan functionality
            await state.update_data(last_urls=urls)

            # Create header
            url_count = len(urls)
            url_word = "URL" if url_count == 1 else "URLs"
            count_text = f"Analyzed {url_count} {url_word}"
            count_padded = count_text + " " * (25 - len(count_text))

            header = (
                "╭───────────────────────────╮\n"
                "│   ✅  BULK SCAN COMPLETE  │\n"
                f"│   {count_padded}│\n"
                "│   📄 " + document.file_name[:20].ljust(20) + " │\n"
                "╰───────────────────────────╯"
            )

            await message.answer(header)

            # Send each result
            footer = get_footer()
            for i, result in enumerate(results):
                msg_text = result.rstrip() + footer

                # Add Quick Rescan button
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Quick Rescan", callback_data=f"quick_rescan_{i}")]
                ])

                await message.answer(msg_text, reply_markup=keyboard)

                # Small delay between messages to avoid flooding
                if i < len(results) - 1:
                    await asyncio.sleep(0.1)

    except UnicodeDecodeError:
        logger.error(f"Failed to decode file {document.file_name}")
        error_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  DECODE ERROR        │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Could not read file content.\n"
            "\n"
            "Please ensure the file is:\n"
            "  • Plain text format (.txt)\n"
            "  • UTF-8 encoding\n"
            "  • Not corrupted"
            + get_footer()
        )
        await message.answer(error_msg)
    except Exception as e:
        logger.error(f"Error in bulk scan: {str(e)}")
        error_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  PROCESSING ERROR    │\n"
            "╰───────────────────────────╯\n"
            "\n"
            f"{str(e)[:100]}\n"
            "\n"
            "Please try again or contact support."
            + get_footer()
        )
        await message.answer(error_msg)


# =============================================================================
# MEDIA HANDLER - Handle non-text content
# =============================================================================

@router.message(F.photo | F.video | F.audio | F.voice | F.sticker)
async def handle_media(message: Message):
    """Handle non-document media messages."""
    media_msg = (
        "╭───────────────────────────╮\n"
        "│   ❌  TEXT ONLY           │\n"
        "╰───────────────────────────╯\n"
        "\n"
        "Please use text commands.\n"
        "\n"
        "┌─ AVAILABLE COMMANDS ──────\n"
        "│\n"
        "│  ›  /url example.com\n"
        "│  ›  /bulk (reply to .txt)\n"
        "│  ›  /help for more info\n"
        "│\n"
        "└────────────────────────────"
        + get_footer()
    )
    await message.answer(media_msg)


@router.message(F.document)
async def handle_document(message: Message):
    """Handle document uploads with helpful instructions."""
    document = message.document
    file_name = document.file_name or "unknown"

    if file_name.endswith('.txt'):
        # Helpful message for .txt files
        doc_msg = (
            "╭───────────────────────────╮\n"
            "│   📄  TEXT FILE DETECTED  │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "To scan URLs from this file:\n"
            "\n"
            "┌─ NEXT STEP ───────────────\n"
            "│\n"
            "│  1️⃣ Reply to this file\n"
            "│  2️⃣ Type: /bulk\n"
            "│  3️⃣ Wait for results! ✨\n"
            "│\n"
            "└────────────────────────────\n"
            "\n"
            "💡 The file should contain URLs,\n"
            "one per line."
            + get_footer()
        )
    else:
        # For other file types
        doc_msg = (
            "╭───────────────────────────╮\n"
            "│   ❌  UNSUPPORTED FILE    │\n"
            "╰───────────────────────────╯\n"
            "\n"
            "Only .txt files are supported.\n"
            "\n"
            "┌─ BULK SCANNING ───────────\n"
            "│\n"
            "│  1️⃣ Create a .txt file with\n"
            "│     URLs (one per line)\n"
            "│\n"
            "│  2️⃣ Upload the file\n"
            "│\n"
            "│  3️⃣ Reply with /bulk\n"
            "│\n"
            "└────────────────────────────"
            + get_footer()
        )

    await message.answer(doc_msg)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main():
    """Main function to start the bot."""
    logger.info("Starting bot with aiogram 3.x...")
    logger.info(f"Bot username: @{Config.BOT_USERNAME}")
    logger.info(f"Owner ID: {Config.OWNER_USER_ID}")

    # Initialize database and migrate from JSON if needed
    logger.info("Initializing database...")
    try:
        await async_migrate_to_database()
        logger.info("Database ready")
    except Exception as e:
        logger.error(f"Database initialization failed (will use JSON fallback): {e}")

    # Log performance optimization status
    logger.info("Performance optimizations enabled:")
    logger.info("  - Native async (no sync-to-async bridge)")
    logger.info("  - HTTP connection pooling (100 total, 10 per host)")
    logger.info("  - SQLite database with async operations")
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
    dp = Dispatcher(storage=SQLiteStorage())

    # Include router
    dp.include_router(router)

    # Set up graceful shutdown
    async def on_shutdown():
        """
        Handle graceful shutdown of all bot resources.
        
        Cleanup order:
        1. Stop accepting new requests
        2. Close HTTP client (drain connections)
        3. Close bot session
        4. Close database connections
        5. Cancel pending tasks
        """
        logger.info("=" * 60)
        logger.info("GRACEFUL SHUTDOWN INITIATED")
        logger.info("=" * 60)
        
        shutdown_steps = []
        
        # Step 1: Close HTTP client
        try:
            logger.info("Closing HTTP client...")
            await close_http_client()
            shutdown_steps.append("✓ HTTP client closed")
        except Exception as e:
            logger.error(f"Error closing HTTP client: {e}")
            shutdown_steps.append(f"✗ HTTP client error: {e}")
        
        # Step 2: Close bot session
        try:
            logger.info("Closing bot session...")
            await bot.session.close()
            shutdown_steps.append("✓ Bot session closed")
        except Exception as e:
            logger.error(f"Error closing bot session: {e}")
            shutdown_steps.append(f"✗ Bot session error: {e}")
        
        # Step 3: Close database connections
        try:
            logger.info("Closing database connections...")
            from database import _db_instance
            if _db_instance:
                # aiosqlite connections close automatically via context manager
                # But we can mark it as closed
                _db_instance._initialized = False
                shutdown_steps.append("✓ Database connections closed")
            else:
                shutdown_steps.append("- Database not initialized")
        except Exception as e:
            logger.error(f"Error closing database: {e}")
            shutdown_steps.append(f"✗ Database error: {e}")
        
        # Step 4: Cancel pending tasks
        try:
            logger.info("Cancelling pending tasks...")
            pending_tasks = [
                task for task in asyncio.all_tasks()
                if task is not asyncio.current_task()
            ]
            
            if pending_tasks:
                for task in pending_tasks:
                    task.cancel()
                
                # Wait for tasks to complete cancellation
                await asyncio.gather(*pending_tasks, return_exceptions=True)
                shutdown_steps.append(f"✓ Cancelled {len(pending_tasks)} pending task(s)")
            else:
                shutdown_steps.append("- No pending tasks")
        except Exception as e:
            logger.error(f"Error cancelling tasks: {e}")
            shutdown_steps.append(f"✗ Task cancellation error: {e}")
        
        # Log shutdown summary
        logger.info("=" * 60)
        logger.info("SHUTDOWN SUMMARY")
        logger.info("=" * 60)
        for step in shutdown_steps:
            logger.info(f"  {step}")
        logger.info("=" * 60)
        logger.info("Shutdown complete. Goodbye!")
        logger.info("=" * 60)

    # Register shutdown callback
    dp.shutdown.register(on_shutdown)

    logger.info("Bot is now polling for updates...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    # Set up signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        """Handle shutdown signals (SIGINT, SIGTERM)."""
        logger.info(f"\nReceived signal {sig}, initiating graceful shutdown...")
        raise KeyboardInterrupt
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("Starting Gateway Hunter Bot...")
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError, SystemExit):
        # Clean exit without traceback when shutdown signal is received
        logger.info("Bot stopped gracefully")
    except Exception as e:
        logger.error(f"Unexpected error during bot execution: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

