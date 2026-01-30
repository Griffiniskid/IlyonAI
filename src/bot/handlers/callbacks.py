"""
Callback query handlers.

Handles all inline button callbacks including:
- buy: Platform selection for Quick Buy
- report: Generate visual report card
- refresh: Re-analyze token with fresh data
- back: Navigation back to analysis
- example: Show example analysis
- ask_ai: AI chat prompt
- asktoken: Token-specific AI questions

Extracted from bot.py lines 2729-2890.
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from src.output.report_card import ReportCardGenerator
from src.monetization.affiliates import get_manager
from .analyze import analyzer, cache, do_analyze
from .start import stats

logger = logging.getLogger(__name__)

# Create router for callback handlers
router = Router()

# Report card generator instance
report_generator = ReportCardGenerator()


@router.callback_query(F.data.startswith("buy:"))
async def callback_buy(cb: CallbackQuery):
    """
    Show platform selection for buying.

    Displays all enabled affiliate bots with their commission rates.
    User can choose which trading bot to use for purchase.

    Extracted from bot.py lines 2729-2789.
    """
    await cb.answer()
    key = cb.data.split(":")[1]

    if key not in cache:
        await cb.message.answer("❌ Данные устарели. Отправь адрес заново.")
        return

    r = cache[key]
    t = r.token
    addr = t.address

    # Get affiliate manager
    affiliate_manager = get_manager()
    enabled = affiliate_manager.enabled_bots

    if not enabled:
        await cb.message.answer(
            "❌ Нет настроенных платформ для покупки.\n"
            "Настройте affiliate ссылки в .env файле."
        )
        return

    # Build platform selection buttons
    platform_buttons = []
    for bot in enabled:
        link = bot.generate_link(addr)
        if link:
            platform_buttons.append([
                InlineKeyboardButton(
                    text=f"{bot.emoji} {bot.name}",
                    url=link
                )
            ])

    # Add back button
    platform_buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back:{key}")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=platform_buttons)

    # Score indicator
    if r.overall_score >= 70:
        score_text = f"🟢 Score: {r.overall_score}/100 — Относительно безопасно"
    elif r.overall_score >= 50:
        score_text = f"🟡 Score: {r.overall_score}/100 — Есть риски"
    else:
        score_text = f"🔴 Score: {r.overall_score}/100 — Высокий риск!"

    await cb.message.answer(
        f"⚡ <b>Выбери платформу для покупки</b>\n\n"
        f"<b>Токен:</b> ${t.symbol}\n"
        f"<b>Цена:</b> ${t.price_usd:.8f}\n"
        f"{score_text}\n\n"
        f"👇 <b>Доступные платформы:</b>",
        reply_markup=kb
    )

    # Track quick buy click
    stats['quick_buys'] += 1
    logger.info(f"💰 Quick Buy opened for {t.symbol} by user {cb.from_user.id}")


@router.callback_query(F.data.startswith("back:"))
async def callback_back(cb: CallbackQuery):
    """
    Go back to token analysis.

    Simply deletes the platform selection message to return to analysis view.

    Extracted from bot.py lines 2792-2806.
    """
    await cb.answer()
    key = cb.data.split(":")[1]

    if key not in cache:
        await cb.message.answer("❌ Данные устарели. Отправь адрес заново.")
        return

    # Delete the platform selection message
    try:
        await cb.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")
        pass


@router.callback_query(F.data == "example")
async def callback_example(cb: CallbackQuery):
    """
    Show example token analysis.

    Uses Bonk token as example (DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263).

    Extracted from bot.py lines 2809-2812.
    """
    await cb.answer("Загружаю пример...")

    # Bonk token address (well-known Solana token)
    example_address = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

    logger.info(f"Example analysis requested by user {cb.from_user.id}")
    await do_analyze(cb.message, example_address)


@router.callback_query(F.data.startswith("report:"))
async def callback_report(cb: CallbackQuery):
    """
    Generate and send visual report card.

    Creates a professional PNG report card with:
    - Token header and score
    - Market data
    - Risk metrics bars
    - Security checks
    - QR code for quick buy

    Extracted from bot.py lines 2846-2874.
    """
    await cb.answer("📸 Генерирую Report Card...")
    key = cb.data.split(":")[1]

    if key not in cache:
        await cb.message.answer("❌ Данные устарели. Повтори анализ.")
        return

    try:
        r = cache[key]
        t = r.token

        # Generate report card image
        img = report_generator.create(r)
        photo = BufferedInputFile(img.read(), filename="report.png")

        # Build caption
        caption = f"🛡️ <b>AI Sentinel Report</b>\n"
        caption += f"${t.symbol} — Score: <b>{r.overall_score}/100</b> ({r.grade})\n\n"
        caption += f"🔒 LP: {'✅ Locked' if t.liquidity_locked else '❌ NOT LOCKED'}\n"
        caption += f"📱 Socials: {t.socials_count}/3\n"
        caption += f"\n⚡ Scan QR to Quick Buy on Trojan"

        # Quick Buy button under image
        affiliate_manager = get_manager()
        quick_buy_link = affiliate_manager.get_primary_buy_link(t.address)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Quick Buy", url=quick_buy_link)]
        ])

        await cb.message.answer_photo(photo=photo, caption=caption, reply_markup=kb)

        logger.info(f"📸 Report card sent for {t.symbol} to user {cb.from_user.id}")

    except Exception as e:
        logger.error(f"Report error: {e}", exc_info=True)
        await cb.message.answer(f"❌ Error: {str(e)[:50]}")


@router.callback_query(F.data.startswith("refresh:"))
async def callback_refresh(cb: CallbackQuery):
    """
    Refresh analysis with fresh data.

    Clears cache and re-analyzes the token to get latest data.

    Extracted from bot.py lines 2877-2889.
    """
    await cb.answer("🔄 Обновляю...")
    key = cb.data.split(":")[1]

    if key in cache:
        addr = cache[key].token.address

        # Clear cache
        del cache[key]

        # Clear analyzer cache if exists
        if hasattr(analyzer, '_cache') and addr in analyzer._cache:
            del analyzer._cache[addr]

        logger.info(f"🔄 Refresh requested for {addr[:8]}... by user {cb.from_user.id}")

        # Re-analyze
        await do_analyze(cb.message, addr)
    else:
        await cb.message.answer("❌ Отправь адрес заново")


@router.callback_query(F.data.startswith("deep:"))
async def callback_deep(cb: CallbackQuery):
    """
    Run deep analysis with enhanced AI analysis.

    Performs comprehensive analysis including:
    - Full technical analysis
    - Smart contract review
    - Holder distribution check
    - AI-powered risk assessment
    """
    await cb.answer("Starting deep analysis...")
    key = cb.data.split(":")[1]

    if key not in cache:
        await cb.message.answer("❌ Data expired. Send the address again.")
        return

    addr = cache[key].token.address

    # Send status message
    status = await cb.message.answer(
        "🔍 <b>Deep Analysis</b>\n\n"
        "Running comprehensive analysis with:\n"
        "• Full technical analysis\n"
        "• Smart contract review\n"
        "• Holder distribution check\n"
        "• AI-powered risk assessment\n\n"
        "⏱ Please wait..."
    )

    logger.info(f"🔬 Deep analysis requested for {addr[:8]}... by user {cb.from_user.id}")

    # Clear cache for fresh analysis
    if key in cache:
        del cache[key]

    # Run deep analysis
    await do_analyze(status, addr, mode="full")


@router.callback_query(F.data.startswith("bots:"))
async def callback_bots(cb: CallbackQuery):
    """
    Show all affiliate bot options.

    Alternative to the buy: callback, shows all bots with commission rates.
    """
    await cb.answer()
    address = cb.data.split(":")[1]

    # Get affiliate manager
    affiliate_manager = get_manager()
    enabled = affiliate_manager.enabled_bots

    if not enabled:
        await cb.message.answer(
            "❌ Нет настроенных платформ для покупки.\n"
            "Настройте affiliate ссылки в .env файле."
        )
        return

    # Build bot list with commission rates
    platform_buttons = []
    for bot in enabled:
        link = bot.generate_link(address)
        if link:
            platform_buttons.append([
                InlineKeyboardButton(
                    text=f"{bot.emoji} {bot.name} ({bot.commission})",
                    url=link
                )
            ])

    # Add back button
    platform_buttons.append([
        InlineKeyboardButton(text="⬅️ Back", callback_data=f"back_bots:{address}")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=platform_buttons)

    await cb.message.answer(
        "🤖 <b>Quick Buy Options</b>\n\n"
        "Choose your preferred trading bot:",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("back_bots:"))
async def callback_back_bots(cb: CallbackQuery):
    """Delete the bots selection message"""
    await cb.answer()

    try:
        await cb.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")
        pass


@router.callback_query(F.data.startswith("share:"))
async def callback_share_blink(cb: CallbackQuery):
    """
    Generate shareable Blink URL for viral Twitter sharing.

    Creates a Solana Actions-compatible Blink that renders as an
    interactive card on Twitter/X, allowing anyone to verify the token.
    """
    from urllib.parse import quote

    from src.config import settings

    await cb.answer("Generating shareable link...")
    key = cb.data.split(":")[1]

    if key not in cache:
        await cb.message.answer("❌ Data expired. Please analyze again.")
        return

    # Check if Blinks are enabled
    if not settings.blinks_enabled:
        await cb.message.answer(
            "🔗 <b>Shareable Blinks</b>\n\n"
            "This feature is currently disabled.\n"
            "Enable it by setting BLINKS_ENABLED=true in your .env file."
        )
        return

    try:
        r = cache[key]
        t = r.token

        # Create blink via service
        from src.api.services.blink_service import get_blink_service
        blink_service = get_blink_service()

        blink = await blink_service.create_blink(
            token_address=t.address,
            analysis_result=r,
            telegram_id=cb.from_user.id,
        )

        blink_url = blink["url"]

        # Twitter share text
        verdict_emoji = "✅" if r.overall_score >= 70 else "⚠️" if r.overall_score >= 50 else "🚨"
        twitter_text = (
            f"{verdict_emoji} Verified ${t.symbol} on AI Sentinel\n"
            f"Score: {r.overall_score}/100 ({r.grade})\n"
            f"Verdict: {getattr(t, 'ai_verdict', 'N/A')}\n\n"
            f"Check it yourself:"
        )

        # Build Twitter share URL
        twitter_url = (
            f"https://twitter.com/intent/tweet?"
            f"text={quote(twitter_text)}&url={quote(blink_url)}"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🐦 Share on Twitter/X", url=twitter_url)],
            [InlineKeyboardButton(text="📋 Copy Link", callback_data=f"copy_blink:{blink['id']}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data=f"back:{key}")]
        ])

        await cb.message.answer(
            f"🔗 <b>Share this security analysis</b>\n\n"
            f"<b>Token:</b> ${t.symbol}\n"
            f"<b>Score:</b> {r.overall_score}/100 ({r.grade})\n\n"
            f"<b>Blink URL:</b>\n<code>{blink_url}</code>\n\n"
            f"Share this link on Twitter/X and it will render as an interactive card. "
            f"Anyone can click the link to verify ${t.symbol} instantly!",
            reply_markup=kb
        )

        # Track share
        stats['shares'] = stats.get('shares', 0) + 1
        logger.info(f"🔗 Blink created for {t.symbol} by user {cb.from_user.id}: {blink['id']}")

    except Exception as e:
        logger.error(f"Error creating blink: {e}", exc_info=True)
        await cb.message.answer(f"❌ Error creating shareable link: {str(e)[:100]}")


@router.callback_query(F.data.startswith("copy_blink:"))
async def callback_copy_blink(cb: CallbackQuery):
    """Show blink URL for copying"""
    from src.config import settings

    blink_id = cb.data.split(":")[1]
    blink_url = f"{settings.actions_base_url}/blinks/{blink_id}"

    await cb.answer(f"Link: {blink_url}", show_alert=True)
