"""
Start command and help handlers.

Handles /start, /help, and /stats commands.
Includes referral system integration for viral growth.
"""

import logging
from datetime import datetime
from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command

from src.core.analyzer import TokenAnalyzer
from src.monetization.affiliates import get_trojan_ref_link
from src.growth.referral import get_referral_manager
from src.storage.database import get_database

logger = logging.getLogger(__name__)

# Create router for start commands
router = Router()

# Shared analyzer instance for address validation
analyzer = TokenAnalyzer()

# Statistics tracking (simple in-memory, DB used for persistence)
stats = {
    'start': datetime.now(),
    'users': set(),
    'analyses': 0,
    'quick_buys': 0,
    'ai_chats': 0,
}


@router.message(CommandStart())
async def cmd_start(msg: Message):
    """
    Handle /start command with deep link support.

    Supports:
    - /start - Welcome message
    - /start {token_address} - Direct analysis
    - /start ref_{code} - Referral tracking
    """
    # Track user in memory
    stats['users'].add(msg.from_user.id)

    # Track user in database
    try:
        db = await get_database()
        await db.get_or_create_user(
            telegram_id=msg.from_user.id,
            username=msg.from_user.username,
            first_name=msg.from_user.first_name
        )
    except Exception as e:
        logger.debug(f"Database tracking skipped: {e}")

    # Check for deep link parameters
    args = msg.text.split()
    referral_msg = ""

    if len(args) > 1:
        start_param = args[1]

        # Handle Blink deep links (blink_{id})
        if start_param.startswith("blink_"):
            blink_id = start_param[6:]  # Remove "blink_" prefix
            logger.info(f"Blink deep link: {blink_id}")

            try:
                from src.api.services.blink_service import get_blink_service
                blink_service = get_blink_service()
                blink = await blink_service.get_blink(blink_id)

                if blink:
                    # Track the visit
                    await blink_service.track_event(blink_id, "view")

                    # Analyze the token from the blink
                    from .analyze import do_analyze
                    await do_analyze(msg, blink.token_address)
                    return
                else:
                    await msg.answer(
                        "🔗 <b>Blink not found</b>\n\n"
                        "This shareable link has expired or doesn't exist.\n"
                        "Send a token address to analyze it directly."
                    )
                    return
            except Exception as e:
                logger.error(f"Error processing blink deep link: {e}")
                await msg.answer(
                    "🔗 <b>Error loading Blink</b>\n\n"
                    "Something went wrong. Please try again or send a token address directly."
                )
                return

        # Handle check_ deep links (from verification results)
        if start_param.startswith("check_"):
            token_prefix = start_param[6:]  # Remove "check_" prefix
            logger.info(f"Check deep link for token prefix: {token_prefix}")
            await msg.answer(
                f"🔍 <b>Token Verification</b>\n\n"
                f"Send the full token address to analyze it.\n\n"
                f"<i>Partial address from link: {token_prefix}...</i>"
            )
            return

        # Process with referral manager
        referral_manager = get_referral_manager()
        result = await referral_manager.process_start_parameter(
            msg.from_user.id,
            start_param
        )

        if result["type"] == "token":
            # Direct token analysis
            logger.info(f"Deep link analysis for {result['token_address'][:8]}...")
            from .analyze import do_analyze
            await do_analyze(msg, result["token_address"])
            return

        elif result["type"] == "referral" and result["success"]:
            # Successful referral - show welcome with referral message
            referrer_name = result.get("referrer_name", "a friend")
            referral_msg = f"\n\n🎉 <i>Ты пришёл по приглашению от {referrer_name}!</i>"
            logger.info(f"Referral processed: {result['referrer_id']} -> {msg.from_user.id}")

        elif result["type"] == "referral" and result.get("already_referred"):
            logger.debug(f"User already referred: {msg.from_user.id}")

    # Get Trojan ref link
    trojan_ref = get_trojan_ref_link()

    # Get user's referral link for invite button
    try:
        referral_manager = get_referral_manager()
        user_ref_link = await referral_manager.get_referral_link(msg.from_user.id)
    except Exception:
        user_ref_link = None

    # Send welcome message
    welcome_text = f"""
🛡️ <b>AI Sentinel — STRICT Token Analyzer</b>

Привет, <b>{msg.from_user.first_name}</b>!{referral_msg}

Я использую <b>СТРОГИЙ AI-анализ</b> для защиты от скама.

<b>🔍 Проверяю:</b>
• Mint/Freeze Authority
• LP Lock (RugCheck.xyz)
• Twitter, Website, Telegram
• Распределение холдеров
• Торговая активность

<b>⚡ Quick Buy:</b>
Безопасные токены можно купить в 1 клик через Trojan Bot

<b>⚠️ СТРОГИЕ правила:</b>
• Mint Authority ON = макс 50 баллов
• LP не залочен = макс 60 баллов
• Нет соцсетей = макс 40 баллов

<b>📝 Как использовать:</b>
Отправь <b>адрес токена</b> — получишь честный анализ

<i>⚠️ Not financial advice. DYOR!</i>
"""

    # Build keyboard
    keyboard_buttons = [
        [
            InlineKeyboardButton(text="📊 Пример анализа", callback_data="example"),
            InlineKeyboardButton(text="🤖 Спросить AI", callback_data="ask_ai")
        ],
        [
            InlineKeyboardButton(text="⚡ Trojan Bot", url=trojan_ref)
        ]
    ]

    # Add invite button if referral link available
    if user_ref_link:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="👥 Пригласить друзей",
                url=f"https://t.me/share/url?url={user_ref_link}&text=🛡️ AI Sentinel - лучший анализатор токенов!"
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await msg.answer(welcome_text, reply_markup=keyboard)
    logger.info(f"Welcome sent to user {msg.from_user.id}")


@router.message(Command("help"))
async def cmd_help(msg: Message):
    """
    Handle /help command.

    Shows detailed information about:
    - How to analyze tokens
    - Scoring breakdown
    - Quick Buy feature
    - Penalty rules
    - Available commands

    Extracted from bot.py lines 2437-2468.
    """
    help_text = """
🛡️ <b>AI Sentinel — Помощь</b>

<b>🔍 Анализ токена:</b>
Отправь Solana адрес (32-44 символа)

<b>📊 What we check:</b>
• Security (30%) — Mint/Freeze authority, token age
• Liquidity (20%) — Volume, LP Lock status
• Distribution (18%) — Holder concentration
• Social (12%) — Twitter, Website, Telegram
• Activity (12%) — Transaction patterns
• Contract Quality (8%) — Smart contract analysis

<b>⚡ Quick Buy:</b>
После анализа нажми <b>"⚡ Quick Buy"</b> чтобы:
• Открыть Trojan Bot с токеном
• Купить в 1 клик
• Получить MEV-защиту

<b>🚨 Штрафы (СТРОГО):</b>
• Mint ON → макс 50 баллов
• LP не залочен → макс 60 баллов
• 0 соцсетей → макс 40 баллов

<b>📈 Команды:</b>
/start — Начало
/help — Помощь
/ask [вопрос] — Спросить AI
/stats — Статистика
"""

    await msg.answer(help_text)
    logger.info(f"Help sent to user {msg.from_user.id}")


@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    """
    Handle /stats command.

    Shows bot statistics:
    - Total users
    - Total analyses
    - Quick buys count
    - AI chats count
    - Uptime
    - Enabled affiliate bots

    Extracted from bot.py lines 2471-2500.
    """
    uptime = datetime.now() - stats['start']

    # Get enabled affiliates info
    affiliate_manager = get_manager()
    enabled = affiliate_manager.enabled_bots

    affiliate_info = "\n".join([
        f"  • {bot.emoji} {bot.name} ({bot.commission})"
        for bot in enabled
    ]) or "  • Нет активных"

    stats_text = f"""
📊 <b>AI Sentinel Stats</b>

👥 Users: <b>{len(stats['users'])}</b>
🔍 Token Analyses: <b>{stats['analyses']}</b>
⚡ Quick Buys: <b>{stats['quick_buys']}</b>
🤖 AI Chats: <b>{stats['ai_chats']}</b>
⏱ Uptime: <b>{int(uptime.total_seconds()//3600)}h {int((uptime.total_seconds()%3600)//60)}m</b>

<b>🤖 Active Affiliate Bots:</b>
{affiliate_info}

<b>🧠 AI Provider:</b>
  • GPT (Technical Analysis)
"""

    await msg.answer(stats_text)
    logger.info(f"Stats sent to user {msg.from_user.id}")


def increment_stat(key: str):
    """
    Increment a statistic counter.

    Args:
        key: Stat key to increment ('analyses', 'quick_buys', 'ai_chats')
    """
    if key in stats:
        stats[key] += 1
        logger.debug(f"Stat incremented: {key}={stats[key]}")
