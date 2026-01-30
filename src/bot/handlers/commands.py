"""
Additional command handlers.

Handles /deep, /quick, and /trending commands for different analysis modes.
"""

import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from .analyze import do_analyze, analyzer

logger = logging.getLogger(__name__)

# Create router for additional commands
router = Router()


@router.message(Command("deep"))
async def cmd_deep(msg: Message):
    """
    Handle /deep command for comprehensive analysis.

    Usage: /deep {token_address}

    Runs full analysis with enhanced AI analysis.
    """
    args = msg.text.split()

    if len(args) < 2:
        await msg.answer(
            "📊 <b>Deep Analysis</b>\n\n"
            "<b>Usage:</b> /deep &lt;token_address&gt;\n\n"
            "Runs comprehensive analysis with:\n"
            "• Full technical analysis\n"
            "• Smart contract review\n"
            "• Holder distribution check\n"
            "• AI-powered risk assessment\n\n"
            "<b>Example:</b>\n"
            "<code>/deep So11111111111111111111111111111111111111112</code>"
        )
        return

    address = args[1].strip()

    if not analyzer.is_valid_address(address):
        await msg.answer("❌ Invalid Solana address")
        return

    logger.info(f"Deep analysis requested for {address[:8]}... by user {msg.from_user.id}")
    await do_analyze(msg, address, mode="full")


@router.message(Command("quick"))
async def cmd_quick(msg: Message):
    """
    Handle /quick command for fast security check.

    Usage: /quick {token_address}

    Runs quick analysis with:
    - Security checks (mint, freeze, LP)
    - Basic market data
    - GPT-4o-mini analysis only

    Takes ~5 seconds.
    """
    args = msg.text.split()

    if len(args) < 2:
        await msg.answer(
            "⚡ <b>Quick Analysis</b>\n\n"
            "<b>Usage:</b> /quick &lt;token_address&gt;\n\n"
            "Runs fast security check with:\n"
            "• Mint/Freeze authority check\n"
            "• LP lock verification\n"
            "• Basic market data\n"
            "• GPT-4o-mini analysis\n\n"
            "⏱ Takes ~5 seconds\n\n"
            "<b>Example:</b>\n"
            "<code>/quick So11111111111111111111111111111111111111112</code>"
        )
        return

    address = args[1].strip()

    if not analyzer.is_valid_address(address):
        await msg.answer("❌ Invalid Solana address")
        return

    logger.info(f"Quick analysis requested for {address[:8]}... by user {msg.from_user.id}")
    await do_analyze(msg, address, mode="quick")


@router.message(Command("trending"))
async def cmd_trending(msg: Message):
    """
    Handle /trending command for trending tokens.

    Shows top trending Solana tokens from DexScreener.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from src.data.dexscreener import DexScreenerClient

    logger.info(f"Trending command called by user {msg.from_user.id}")

    # Send loading message
    status = await msg.answer("🔥 <b>Loading trending tokens...</b>")

    try:
        async with DexScreenerClient() as client:
            # Fetch trending Solana tokens
            trending = await client.get_trending_tokens(limit=10)

        if not trending:
            await status.edit_text(
                "🔥 <b>Trending Solana Tokens</b>\n\n"
                "❌ Could not fetch trending tokens.\n\n"
                "Please try again later or send a token address directly."
            )
            return

        # Build trending list text
        text = "🔥 <b>Trending Solana Tokens</b>\n\n"

        keyboard_buttons = []

        for i, token in enumerate(trending[:8], 1):
            symbol = token.get("symbol", "???")
            name = token.get("name", "Unknown")[:20]
            price = token.get("priceUsd", 0)
            volume = token.get("volume24h", 0)
            address = token.get("address", "")

            # Format price
            if price:
                price_float = float(price)
                if price_float < 0.0001:
                    price_str = f"${price_float:.8f}"
                elif price_float < 1:
                    price_str = f"${price_float:.6f}"
                else:
                    price_str = f"${price_float:.4f}"
            else:
                price_str = "N/A"

            # Format volume
            if volume:
                vol_float = float(volume)
                if vol_float >= 1_000_000:
                    vol_str = f"${vol_float/1_000_000:.1f}M"
                elif vol_float >= 1_000:
                    vol_str = f"${vol_float/1_000:.1f}K"
                else:
                    vol_str = f"${vol_float:.0f}"
            else:
                vol_str = "N/A"

            text += f"<b>{i}. ${symbol}</b> - {name}\n"
            text += f"   💰 {price_str} | 📊 Vol: {vol_str}\n\n"

            # Add analyze button for top 4
            if i <= 4 and address:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"🔍 Analyze ${symbol}",
                        callback_data=f"analyze:{address[:32]}"
                    )
                ])

        text += "<i>Tap a button to analyze or send any token address</i>"

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None

        await status.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Trending fetch error: {e}")
        await status.edit_text(
            "🔥 <b>Trending Solana Tokens</b>\n\n"
            "❌ Error fetching trending tokens.\n\n"
            "Please try again later or send a token address directly."
        )


@router.message(Command("portfolio"))
async def cmd_portfolio(msg: Message):
    """
    Handle /portfolio command for wallet tracking.

    Allows users to track their token portfolio.
    Future feature - currently placeholder.
    """
    logger.info(f"Portfolio command called by user {msg.from_user.id}")

    await msg.answer(
        "💼 <b>Portfolio Tracking</b>\n\n"
        "This feature is coming soon!\n\n"
        "You'll be able to:\n"
        "• Add your wallet address\n"
        "• Track token holdings\n"
        "• Get alerts on risk changes\n"
        "• View performance metrics\n\n"
        "Stay tuned! 📊"
    )


@router.message(Command("alerts"))
async def cmd_alerts(msg: Message):
    """
    Handle /alerts command for price/risk alerts.

    Allows users to set up alerts for tokens.
    Future feature - currently placeholder.
    """
    logger.info(f"Alerts command called by user {msg.from_user.id}")

    await msg.answer(
        "🔔 <b>Token Alerts</b>\n\n"
        "This feature is coming soon!\n\n"
        "You'll be able to set:\n"
        "• Price alerts (% change)\n"
        "• Risk score changes\n"
        "• LP unlock warnings\n"
        "• Whale movement alerts\n\n"
        "We'll notify you instantly! ⚡"
    )


@router.message(Command("compare"))
async def cmd_compare(msg: Message):
    """
    Handle /compare command for comparing tokens.

    Allows users to compare multiple tokens side-by-side.
    Future feature - currently placeholder.
    """
    args = msg.text.split()

    if len(args) < 3:
        await msg.answer(
            "⚖️ <b>Token Comparison</b>\n\n"
            "<b>Usage:</b> /compare &lt;address1&gt; &lt;address2&gt;\n\n"
            "This feature is coming soon!\n\n"
            "You'll be able to:\n"
            "• Compare scores side-by-side\n"
            "• See risk differences\n"
            "• Compare holder distribution\n"
            "• View relative performance\n\n"
            "<b>Example:</b>\n"
            "<code>/compare TokenA123... TokenB456...</code>"
        )
        return

    logger.info(f"Compare command called by user {msg.from_user.id}")
    await msg.answer("⚖️ Token comparison feature coming soon! For now, analyze tokens individually.")
