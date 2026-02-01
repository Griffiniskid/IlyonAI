"""
Text message formatters for Telegram bot.

This module provides functions for formatting analysis results into
well-structured Telegram messages with HTML markup, emojis, and
proper formatting for readability.
"""

import html
import logging
from typing import List

from src.core.models import AnalysisResult, TokenInfo

logger = logging.getLogger(__name__)


def format_analysis_message(result: AnalysisResult) -> str:
    """
    Format full analysis result as Telegram HTML message.

    Creates a comprehensive analysis message with:
    - Token header with score and grade
    - Market data (price, mcap, liquidity, volume)
    - Security checks (mint/freeze authority, LP lock)
    - Risk scores breakdown
    - Risk factors and positive factors
    - AI analysis summary
    - Final recommendation

    Args:
        result: AnalysisResult with complete token analysis

    Returns:
        Formatted HTML message for Telegram
    """
    t = result.token

    # Score emoji based on overall score
    if result.overall_score >= 80:
        score_emoji = "🟢"
    elif result.overall_score >= 60:
        score_emoji = "🟡"
    elif result.overall_score >= 40:
        score_emoji = "🟠"
    else:
        score_emoji = "🔴"

    # Build message
    msg = f"""
{score_emoji} <b>{t.symbol}</b> — Score: {result.overall_score}/100 ({result.grade})
<code>{t.address}</code>

💰 <b>Price:</b> ${t.price_usd:.8f}
📊 <b>Market Cap:</b> {format_number(t.market_cap)}
💧 <b>Liquidity:</b> {format_number(t.liquidity_usd)} {"🔒" if t.liquidity_locked else "⚠️"}
📈 <b>Volume 24h:</b> {format_number(t.volume_24h)}
"""

    # Age info if available
    if t.age_hours > 0:
        age_str = format_age(t.age_hours)
        msg += f"🕐 <b>Age:</b> {age_str}\n"

    # Price change if significant
    if t.price_change_24h != 0:
        change_emoji = "📈" if t.price_change_24h > 0 else "📉"
        msg += f"{change_emoji} <b>24h Change:</b> {t.price_change_24h:+.1f}%\n"

    msg += "\n🔐 <b>Security</b>\n"
    msg += f"├ Mint Authority: {'❌ Enabled' if t.mint_authority_enabled else '✅ Disabled'}\n"
    msg += f"├ Freeze Authority: {'❌ Enabled' if t.freeze_authority_enabled else '✅ Disabled'}\n"
    msg += f"├ LP Lock: {'✅ Locked' if t.liquidity_locked else '❌ Not Locked'}"

    # LP lock percentage if available
    if t.liquidity_locked and t.lp_lock_percent > 0:
        msg += f" ({t.lp_lock_percent:.0f}%)"
    msg += "\n"

    # Honeypot status
    if t.honeypot_checked:
        honeypot_status = t.honeypot_status
        if honeypot_status == "honeypot":
            msg += f"└ 🍯 <b>HONEYPOT DETECTED!</b>\n"
        elif honeypot_status == "extreme_tax":
            tax = t.honeypot_sell_tax_percent or 0
            msg += f"└ 💸 Extreme Tax: {tax:.1f}%\n"
        elif honeypot_status == "high_tax":
            tax = t.honeypot_sell_tax_percent or 0
            msg += f"└ 💸 High Tax: {tax:.1f}%\n"
        elif honeypot_status == "safe":
            msg += f"└ ✅ Sellable: Yes\n"
        else:
            msg += f"└ ❓ Sell Check: Unverified\n"

    # Social media presence
    if t.has_twitter or t.has_website or t.has_telegram:
        msg += "\n🌐 <b>Socials</b>\n"
        if t.has_twitter:
            msg += "├ ✅ Twitter\n"
        if t.has_website:
            msg += "├ ✅ Website\n"
        if t.has_telegram:
            msg += "└ ✅ Telegram\n"

    # Risk scores breakdown
    msg += "\n📊 <b>Scores</b>\n"
    msg += f"├ Safety: {result.safety_score}/100\n"
    msg += f"├ Liquidity: {result.liquidity_score}/100\n"
    msg += f"├ Distribution: {result.distribution_score}/100\n"
    msg += f"├ Social: {result.social_score}/100\n"
    msg += f"├ Activity: {result.activity_score}/100\n"
    msg += f"├ Honeypot: {result.honeypot_score}/100\n"

    msg += f"└ <b>Overall: {result.overall_score}/100</b>\n"

    # Holder analysis if available
    if t.top_holder_pct > 0:
        msg += f"\n🐋 <b>Top Holder:</b> {t.top_holder_pct:.1f}% of supply\n"

    # Risk factors
    if t.risk_factors:
        msg += "\n⚠️ <b>Risk Factors:</b>\n"
        for risk in t.risk_factors[:5]:  # Limit to top 5
            # Clean up emoji spacing and escape HTML characters
            risk_clean = html.escape(risk.strip())
            msg += f"• {risk_clean}\n"

    # Positive factors
    if t.positive_factors:
        msg += "\n✅ <b>Positive Factors:</b>\n"
        for good in t.positive_factors[:3]:  # Limit to top 3
            # Escape HTML characters
            good_clean = html.escape(good.strip())
            msg += f"• {good_clean}\n"

    # AI analysis summary
    if result.token.ai_narrative:
        # If we have a dedicated narrative block (from Grok), show it
        msg += f"\n{result.token.ai_narrative}\n"
    elif result.ai_analysis:
        ai_text = html.escape(result.ai_analysis[:500])
        msg += f"\n🤖 <b>AI Analysis:</b>\n{ai_text}\n"

    # Final recommendation
    msg += f"\n<b>{result.recommendation}</b>"

    # RugCheck score if available
    if t.rugcheck_score > 0:
        msg += f"\n\n🔍 RugCheck Score: {t.rugcheck_score}/100"

    return msg.strip()


def format_quick_analysis(result: AnalysisResult) -> str:
    """
    Format quick (minimal) analysis message.

    Creates a compact one-screen summary with essential info only.
    Useful for quick checks or mobile viewing.

    Args:
        result: AnalysisResult

    Returns:
        Compact formatted message
    """
    t = result.token

    # Simple status indicator
    if result.overall_score >= 70:
        status = "✅ SAFE"
    elif result.overall_score >= 40:
        status = "⚠️ RISKY"
    else:
        status = "❌ DANGEROUS"

    # Honeypot indicator for quick view
    if t.honeypot_checked and t.honeypot_is_honeypot:
        honeypot_indicator = "🍯 HONEYPOT!"
    elif t.honeypot_checked and t.honeypot_status == "extreme_tax":
        honeypot_indicator = f"💸 {t.honeypot_sell_tax_percent:.0f}% tax"
    elif t.honeypot_checked and t.honeypot_status == "safe":
        honeypot_indicator = "✅ Sellable"
    else:
        honeypot_indicator = "❓"

    msg = f"""
{status} <b>${t.symbol}</b> — {result.overall_score}/100 ({result.grade})

🔐 Mint: {'✅' if not t.mint_authority_enabled else '❌'} | Freeze: {'✅' if not t.freeze_authority_enabled else '❌'} | LP: {'🔒' if t.liquidity_locked else '⚠️'}
🍯 Sell: {honeypot_indicator}
💧 Liquidity: {format_number(t.liquidity_usd)}
📊 MCap: {format_number(t.market_cap)}

<code>{t.address}</code>

<b>{result.recommendation}</b>
"""

    return msg.strip()


def format_error_message(error: str, address: str = "") -> str:
    """
    Format error message for Telegram.

    Args:
        error: Error description
        address: Optional token address

    Returns:
        Formatted error message
    """
    msg = "❌ <b>Analysis Failed</b>\n\n"

    if address:
        msg += f"Token: <code>{html.escape(address)}</code>\n\n"

    msg += f"Error: {html.escape(error)}\n\n"
    msg += "Please try again or check if the address is correct."

    return msg


def format_loading_message(address: str, mode: str = "standard") -> str:
    """
    Format loading/processing message.

    Args:
        address: Token address being analyzed
        mode: Analysis mode (quick/standard/full)

    Returns:
        Formatted loading message
    """
    mode_emoji = {
        "quick": "⚡",
        "standard": "🔍",
        "full": "🔬"
    }

    emoji = mode_emoji.get(mode, "🔍")
    mode_name = mode.upper()

    msg = f"""
{emoji} <b>Analyzing Token...</b>

Mode: {mode_name}
Address: <code>{address[:8]}...{address[-6:]}</code>

Please wait...
"""

    return msg.strip()


def format_number(n: float) -> str:
    """
    Format number with K/M/B suffix.

    Args:
        n: Number to format

    Returns:
        Formatted string like "$1.2M", "$450K", etc.
    """
    if n >= 1e9:
        return f"${n/1e9:.2f}B"
    elif n >= 1e6:
        return f"${n/1e6:.2f}M"
    elif n >= 1e3:
        return f"${n/1e3:.1f}K"
    else:
        return f"${n:.0f}"


def format_age(hours: float) -> str:
    """
    Format age in human-readable format.

    Args:
        hours: Age in hours

    Returns:
        Formatted age string
    """
    if hours < 1:
        minutes = int(hours * 60)
        return f"{minutes}m"
    elif hours < 24:
        return f"{hours:.1f}h"
    elif hours < 168:  # 7 days
        days = hours / 24
        return f"{days:.1f}d"
    else:
        weeks = hours / 168
        return f"{weeks:.1f}w"


def format_holders_list(token: TokenInfo, limit: int = 5) -> str:
    """
    Format top holders list.

    Args:
        token: TokenInfo with holder data
        limit: Number of holders to show

    Returns:
        Formatted holders list
    """
    if not token.top_holders:
        return "No holder data available"

    msg = "🐋 <b>Top Holders:</b>\n\n"

    total_supply = token.supply / (10 ** token.decimals) if token.supply > 0 else 1

    for i, holder in enumerate(token.top_holders[:limit], 1):
        addr = holder.get('address', '')
        amount = holder.get('amount', 0)

        if total_supply > 0:
            pct = (amount / total_supply) * 100
        else:
            pct = 0

        # Shorten address
        addr_short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr

        msg += f"{i}. <code>{addr_short}</code> — {pct:.2f}%\n"

    # Total concentration
    if token.holder_concentration > 0:
        msg += f"\n📊 Top 10 hold: {token.holder_concentration:.1f}%"

    return msg


def format_socials(token: TokenInfo) -> str:
    """
    Format social media links.

    Args:
        token: TokenInfo with social links

    Returns:
        Formatted socials message
    """
    if token.socials_count == 0:
        return "❌ No social media links found"

    msg = "🌐 <b>Social Links:</b>\n\n"

    if token.has_twitter and token.twitter_url:
        msg += f"🐦 <a href='{token.twitter_url}'>Twitter</a>\n"

    if token.has_website and token.website_url:
        msg += f"🌐 <a href='{token.website_url}'>Website</a>\n"

    if token.has_telegram and token.telegram_url:
        msg += f"💬 <a href='{token.telegram_url}'>Telegram</a>\n"

    return msg.strip()


def truncate_text(text: str, max_length: int = 4000) -> str:
    """
    Truncate text to fit Telegram message limit.

    Args:
        text: Text to truncate
        max_length: Maximum length (Telegram limit is 4096)

    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - 3] + "..."
