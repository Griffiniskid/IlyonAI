"""
Token analysis handlers.

Handles token address messages, /ask AI command, and main analysis flow.
Extracted from bot.py lines 2500-2727.
"""

import html
import logging
import re
from typing import Dict, Optional

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from src.core.analyzer import TokenAnalyzer
from src.core.models import AnalysisResult
from src.output.formatter import format_number
from src.monetization.affiliates import get_manager
from .start import stats, increment_stat

logger = logging.getLogger(__name__)

# Create router for analysis handlers
router = Router()

# ═══════════════════════════════════════════════════════════════════════════
# WARNING EXPLANATIONS FOR NEWCOMERS
# ═══════════════════════════════════════════════════════════════════════════
# These explanations help new users understand what each security issue means

WARNING_EXPLANATIONS = {
    # Security flags
    "mint_authority": (
        "🚨 <b>Mint Authority Enabled</b>\n"
        "<i>The creator can print unlimited tokens at any time, crashing the price to zero. "
        "This is how most rug pulls work.</i>"
    ),
    "freeze_authority": (
        "⚠️ <b>Freeze Authority Enabled</b>\n"
        "<i>The creator can freeze your tokens, preventing you from selling. "
        "While sometimes used legitimately, this is a red flag.</i>"
    ),
    "lp_unlocked": (
        "🔓 <b>Liquidity Not Locked</b>\n"
        "<i>The creator can withdraw all liquidity at any time, making your tokens worthless. "
        "Always check for locked LP before buying.</i>"
    ),

    # Holder distribution
    "high_concentration": (
        "📊 <b>High Holder Concentration</b>\n"
        "<i>A small number of wallets hold most of the supply. "
        "They could dump and crash the price instantly.</i>"
    ),
    "dev_wallet_risk": (
        "💼 <b>Developer Wallet Risk</b>\n"
        "<i>The top wallet (likely dev) holds a large percentage. "
        "If they sell, the price will crash significantly.</i>"
    ),
    "suspicious_wallets": (
        "👀 <b>Suspicious Wallets Detected</b>\n"
        "<i>Some wallets show patterns typical of scams: coordinated buying, "
        "connection to known scammers, or bot-like behavior.</i>"
    ),

    # Market flags
    "low_liquidity": (
        "💧 <b>Low Liquidity</b>\n"
        "<i>Not enough money in the pool to sell your tokens at market price. "
        "You may suffer significant slippage or be unable to sell.</i>"
    ),
    "volume_manipulation": (
        "📈 <b>Possible Volume Manipulation</b>\n"
        "<i>Trading volume seems artificially inflated. "
        "Fake volume is used to attract buyers before a dump.</i>"
    ),

    # Honeypot
    "honeypot": (
        "🍯 <b>Honeypot Detected</b>\n"
        "<i>You CANNOT sell this token. The contract blocks all sell transactions. "
        "Any money you put in is lost forever.</i>"
    ),
    "high_sell_tax": (
        "💸 <b>High Sell Tax</b>\n"
        "<i>A large percentage of your sale goes to fees (often to the dev). "
        "You may lose 20-50% or more when selling.</i>"
    ),

    # Deployer/Wallet forensics
    "known_scammer": (
        "⛔ <b>Known Scammer Deployer</b>\n"
        "<i>This token was created by a wallet that has rugged before. "
        "EXTREMELY high probability of scam.</i>"
    ),
    "serial_deployer": (
        "🔴 <b>Serial Token Deployer</b>\n"
        "<i>This wallet has deployed many tokens in a short time, "
        "a common pattern for rug pull operators.</i>"
    ),

    # Social/Website
    "no_socials": (
        "📱 <b>No Social Media</b>\n"
        "<i>Legitimate projects usually have Twitter, Telegram, and a website. "
        "No socials = higher scam probability.</i>"
    ),
    "fake_socials": (
        "🎭 <b>Suspicious Social Links</b>\n"
        "<i>Social media links appear fake or stolen from other projects. "
        "Scammers often copy-paste legitimate project links.</i>"
    ),
    "low_quality_website": (
        "🌐 <b>Low Quality Website</b>\n"
        "<i>The website shows signs of being hastily made: template content, "
        "placeholder text, or copied from other projects.</i>"
    ),
}


def get_warning_explanation(flag_text: str) -> Optional[str]:
    """
    Get a detailed explanation for a warning flag.

    Args:
        flag_text: The flag text to find explanation for

    Returns:
        Detailed explanation or None if no match found
    """
    flag_lower = flag_text.lower()

    # Try to match against known patterns
    for key, explanation in WARNING_EXPLANATIONS.items():
        if key.replace("_", " ") in flag_lower or key.replace("_", "") in flag_lower:
            return explanation

    # Additional pattern matching
    if "mint" in flag_lower and ("enabled" in flag_lower or "on" in flag_lower):
        return WARNING_EXPLANATIONS["mint_authority"]
    if "freeze" in flag_lower and ("enabled" in flag_lower or "on" in flag_lower):
        return WARNING_EXPLANATIONS["freeze_authority"]
    if "lp" in flag_lower and ("unlock" in flag_lower or "not lock" in flag_lower):
        return WARNING_EXPLANATIONS["lp_unlocked"]
    if "honeypot" in flag_lower or "cannot sell" in flag_lower:
        return WARNING_EXPLANATIONS["honeypot"]
    if "tax" in flag_lower and ("high" in flag_lower or "%" in flag_lower):
        return WARNING_EXPLANATIONS["high_sell_tax"]
    if "scammer" in flag_lower or "rug" in flag_lower:
        return WARNING_EXPLANATIONS["known_scammer"]
    if "concentration" in flag_lower or "whale" in flag_lower:
        return WARNING_EXPLANATIONS["high_concentration"]

    return None


# Short explanations for inline display (max ~60 chars)
SHORT_EXPLANATIONS = {
    "mint": "Dev can print unlimited tokens, crashing price",
    "freeze": "Dev can freeze your tokens, blocking sales",
    "lp": "Dev can withdraw liquidity, making tokens worthless",
    "honeypot": "Cannot sell - your money is trapped forever",
    "tax": "High % of your sale goes to dev as fees",
    "scammer": "Deployer has rugged before - very likely scam",
    "concentration": "Few wallets hold most supply - dump risk",
    "whale": "Large holders could crash price by selling",
    "liquidity": "Not enough liquidity to sell at fair price",
    "social": "No socials = higher scam probability",
}


def _get_short_explanation(flag_text: str) -> str:
    """Get a short inline explanation for a flag."""
    flag_lower = flag_text.lower()

    for keyword, explanation in SHORT_EXPLANATIONS.items():
        if keyword in flag_lower:
            return explanation

    # Default fallback
    return "Potential risk detected"

# Shared analyzer instance
analyzer = TokenAnalyzer()

# In-memory cache for analysis results (replace with Redis for production)
cache: Dict[str, AnalysisResult] = {}


@router.message(F.text)
async def handle_text(msg: Message):
    """
    Handle text messages.

    Checks if text is:
    1. Valid Solana token address → analyze
    2. Contains token address → extract and analyze
    3. General question → AI chat

    Extracted from bot.py lines 2518-2535.
    """
    text = msg.text.strip()
    stats['users'].add(msg.from_user.id)

    # Check if it's a valid address
    if analyzer.is_valid_address(text):
        await do_analyze(msg, text)
        return

    # Try to extract address from text
    match = re.search(r'[1-9A-HJ-NP-Za-km-z]{32,44}', text)
    if match and analyzer.is_valid_address(match.group()):
        await do_analyze(msg, match.group())
        return

    # Invalid or unrecognized input - show helpful error
    await msg.answer(
        "❌ <b>Invalid address / Token not found</b>\n\n"
        "Please send a valid Solana token address.\n\n"
        "💡 <b>Tip:</b> Copy the full address from DexScreener or Solscan.\n\n"
        "Example:\n<code>DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263</code>"
    )


async def do_analyze(msg: Message, addr: str, mode: str = "standard"):
    """
    Main token analysis handler.

    Runs full analysis with:
    - DexScreener data
    - RugCheck LP lock verification
    - Socials check
    - Website analysis
    - Multi-LLM AI analysis
    - Strict scoring

    Args:
        msg: Message object
        addr: Solana token address
        mode: Analysis mode ("quick", "standard", "full")

    Extracted from bot.py lines 2538-2727.
    """
    stats['analyses'] += 1

    # Send status message
    status = await msg.answer(
        "🔍 <b>STRICT анализ токена...</b>\n\n"
        "⏳ DexScreener данные...\n"
        "🔒 RugCheck LP Lock...\n"
        "📱 Проверка соцсетей...\n"
        "🌐 Анализ веб-сайта...\n"
        "🤖 AI анализирует риски..."
    )

    try:
        # Run analysis
        r = await analyzer.analyze(addr, mode=mode)

        if not r:
            await status.edit_text(f"❌ Токен не найден!\n<code>{addr}</code>")
            return

        # Cache result
        key = addr[:16]
        cache[key] = r
        t = r.token

        # Format price
        if t.price_usd < 0.0001:
            price = f"${t.price_usd:.8f}"
        elif t.price_usd < 0.01:
            price = f"${t.price_usd:.6f}"
        else:
            price = f"${t.price_usd:.4f}"

        # Status icons
        lp_status = "✅ Locked" if t.liquidity_locked else "❌ NOT LOCKED"
        twitter_icon = "✅" if t.has_twitter else "❌"
        website_icon = "✅" if t.has_website else "❌"
        telegram_icon = "✅" if t.has_telegram else "❌"

        # Build response text (escape user-controllable data)
        token_name = html.escape(t.name)
        token_symbol = html.escape(t.symbol)

        # Get AI data for header display
        ai_verdict = getattr(t, 'ai_verdict', 'CAUTION')
        ai_confidence = getattr(t, 'ai_confidence', 50)

        verdict_emoji_map = {
            "SAFE": "✅",
            "CAUTION": "⚠️",
            "RISKY": "🟠",
            "DANGEROUS": "🔴",
            "SCAM": "⛔"
        }
        verdict_emoji = verdict_emoji_map.get(ai_verdict, "⚠️")

        text = f"""
🛡️ <b>AI Sentinel Analysis</b>

<b>Token:</b> {token_name}
<b>Symbol:</b> ${token_symbol}
<b>Address:</b> <code>{t.address}</code>

━━━━━━━━━━━━━━━━━━━━━
🤖 <b>AI Score: {r.overall_score}/100 (Grade {r.grade})</b>
├ Verdict: {verdict_emoji} <b>{ai_verdict}</b>
└ Confidence: <b>{ai_confidence}%</b>
━━━━━━━━━━━━━━━━━━━━━

💰 <b>Market:</b>
├ Price: <b>{price}</b>
├ MCap: <b>{format_number(t.market_cap)}</b>
├ Liquidity: <b>{format_number(t.liquidity_usd)}</b> {"🔒" if t.liquidity_locked else "⚠️"}
├ Volume 24h: <b>{format_number(t.volume_24h)}</b>
└ Age: <b>{t.age_hours:.1f}h</b> ({t.dex_name})

🔍 <b>Security:</b>
├ Mint: {"✅ Disabled" if not t.mint_authority_enabled else "🚨 ENABLED"}
├ Freeze: {"✅ Disabled" if not t.freeze_authority_enabled else "⚠️ Enabled"}
└ LP Lock: {lp_status}

📊 <b>Metrics (context):</b>
├ 🔒 Safety: <b>{r.safety_score}</b>/100
├ 💧 Liquidity: <b>{r.liquidity_score}</b>/100
├ 📱 Socials: <b>{r.social_score}</b>/100
├ 📊 Distribution: <b>{r.distribution_score}</b>/100
└ 📈 Activity: <b>{r.activity_score}</b>/100

🔍 <b>Holders:</b>
├ Top-1 wallet: <b>{t.top_holder_pct:.1f}%</b> {"🚨" if t.dev_wallet_risk else "✅"}
├ Suspicious: <b>{t.suspicious_wallets}</b> {"⚠️" if t.suspicious_wallets > 0 else "✅"}
└ Concentration: <b>{t.holder_concentration:.0f}%</b>

📱 <b>Socials ({t.socials_count}/3):</b>
├ {twitter_icon} Twitter
├ {website_icon} Website
└ {telegram_icon} Telegram
"""

        # Website Analysis Section
        if t.has_website:
            website_quality = getattr(t, 'website_quality', 0)
            website_legit = getattr(t, 'website_is_legitimate', False)
            website_type = getattr(t, 'ai_website_type', 'unknown')

            quality_emoji = "🟢" if website_quality >= 70 else "🟡" if website_quality >= 40 else "🔴"

            text += f"""
🌐 <b>Website Analysis:</b>
├ Quality: {quality_emoji} <b>{website_quality}/100</b>
├ Legitimate: {"✅" if website_legit else "❌"}
├ Type: <b>{html.escape(str(website_type))}</b>
"""
            website_summary = getattr(t, 'ai_website_summary', '')
            if website_summary:
                summary = website_summary[:100] + "..." if len(website_summary) > 100 else website_summary
                text += f"└ <i>{html.escape(summary)}</i>\n"

        # Price changes
        text += f"""
📈 <b>Price:</b> 5m: {'+' if t.price_change_5m>=0 else ''}{t.price_change_5m:.1f}% | 1h: {'+' if t.price_change_1h>=0 else ''}{t.price_change_1h:.1f}% | 24h: {'+' if t.price_change_24h>=0 else ''}{t.price_change_24h:.1f}%
"""

        # AI Details Section (score/verdict already in header)
        rug_prob = getattr(t, 'ai_rug_probability', 50)

        text += f"""
🎯 <b>Rug Probability:</b> <b>{rug_prob}%</b> {"🚨" if rug_prob > 60 else "⚠️" if rug_prob > 30 else "✅"}
"""

        # AI Summary
        if t.ai_summary:
            text += f"📝 <i>{html.escape(t.ai_summary)}</i>\n"

        # AI Red Flags with explanations for critical ones
        ai_red = getattr(t, 'ai_red_flags', [])
        if ai_red:
            text += "\n🚩 <b>AI Red Flags:</b>\n"
            critical_explained = False
            for flag in ai_red[:4]:
                text += f"• {html.escape(flag)}\n"
                # Add explanation for the first critical flag (most important)
                if not critical_explained:
                    explanation = get_warning_explanation(flag)
                    if explanation:
                        # Extract just the italic explanation part for inline display
                        text += f"  └ <i>⚠️ {_get_short_explanation(flag)}</i>\n"
                        critical_explained = True

        # AI Green Flags (add to show positive signals too)
        ai_green = getattr(t, 'ai_green_flags', [])
        if ai_green:
            text += "\n✅ <b>AI Green Flags:</b>\n"
            for flag in ai_green[:3]:
                text += f"• {html.escape(flag)}\n"

        # Rug detection
        if r.overall_score == 0:
            text += "\n💀 <b>ТОКЕН МЁРТВ / RUG PULLED</b>"

        # Recommendation
        text += f"\n<b>💡 {r.recommendation}</b>"

        text += "\n\n<i>🔒 LP via RugCheck.xyz | 🤖 AI-Primary Scoring</i>"

        # Build keyboard
        if r.overall_score >= 70:
            buy_text = "🟢 ⚡ BUY ⚡ 🟢"
        elif r.overall_score >= 50:
            buy_text = "🟡 ⚡ Buy ⚡"
        else:
            buy_text = "⚡ Buy"

        # Generate direct buy link (same pattern as report card)
        affiliate_manager = get_manager()
        quick_buy_link = affiliate_manager.get_primary_buy_link(addr)

        buttons = [
            # ROW 1: BUY BUTTON - Direct URL (not callback)
            [InlineKeyboardButton(text=buy_text, url=quick_buy_link)],
            # ROW 2: Report Card, Share & Refresh
            [
                InlineKeyboardButton(text="📸 Report", callback_data=f"report:{key}"),
                InlineKeyboardButton(text="🔗 Share", callback_data=f"share:{key}"),
                InlineKeyboardButton(text="🔄 Refresh", callback_data=f"refresh:{key}")
            ],
            # ROW 3: External links
            [
                InlineKeyboardButton(text="📊 DexScreener", url=f"https://dexscreener.com/solana/{addr}"),
                InlineKeyboardButton(text="🔍 RugCheck", url=f"https://rugcheck.xyz/tokens/{addr}")
            ]
        ]

        # Add social links if available
        social_buttons = []
        if t.twitter_url:
            social_buttons.append(InlineKeyboardButton(text="🐦 Twitter", url=t.twitter_url))
        if t.website_url:
            social_buttons.append(InlineKeyboardButton(text="🌐 Website", url=t.website_url))
        if t.telegram_url:
            social_buttons.append(InlineKeyboardButton(text="💬 Telegram", url=t.telegram_url))

        if social_buttons:
            buttons.append(social_buttons)

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await status.edit_text(text, reply_markup=kb)

        # Log completion
        logger.info(
            f"💰 Analysis complete: {t.symbol} | "
            f"Score: {r.overall_score} | Quick Buy ready"
        )

    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        await status.edit_text(f"❌ Ошибка: {html.escape(str(e)[:80])}")
