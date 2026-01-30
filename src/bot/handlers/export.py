"""
Export command handlers for public scammer database.

Provides /export_scammers command for admins to export the scammer database
as JSON for public sharing. This data benefits the entire Solana ecosystem.
"""

import json
import logging
from datetime import datetime
from io import BytesIO

from aiogram import Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command

from src.config import settings
from src.analytics.wallet_forensics import WalletForensicsEngine

logger = logging.getLogger(__name__)

# Create router for export commands
router = Router()

# Shared forensics engine instance
_forensics_engine: WalletForensicsEngine | None = None


def get_forensics_engine() -> WalletForensicsEngine:
    """Get or create shared forensics engine instance."""
    global _forensics_engine
    if _forensics_engine is None:
        _forensics_engine = WalletForensicsEngine(
            solana_rpc_url=settings.solana_rpc_url
        )
    return _forensics_engine


def is_admin(user_id: int) -> bool:
    """Check if user is an admin (in allowed users list)."""
    allowed = settings.get_allowed_user_ids()
    # If no allowed users configured, allow all (for testing)
    # In production, you should configure ALLOWED_USERS
    if not allowed:
        return True
    return user_id in allowed


@router.message(Command("export_scammers"))
async def cmd_export_scammers(msg: Message):
    """
    Handle /export_scammers command.

    Exports the scammer database as JSON file.
    Admin-only command.

    Usage:
        /export_scammers - Export all known scammers and high-risk wallets
        /export_scammers strict - Export only KNOWN_SCAMMER and CRITICAL

    The exported data can be:
    - Uploaded to GitHub for public access
    - Used by other security tools
    - Integrated into DEX frontends or wallets
    """
    # Check admin permission
    if not is_admin(msg.from_user.id):
        await msg.answer(
            "⛔ <b>Access Denied</b>\n\n"
            "This command is restricted to administrators.\n"
            "Contact the bot owner for access."
        )
        logger.warning(f"Unauthorized export attempt by user {msg.from_user.id}")
        return

    # Parse arguments
    args = msg.text.split()
    strict_mode = len(args) > 1 and args[1].lower() == "strict"

    await msg.answer(
        "📊 <b>Generating Scammer Database Export...</b>\n\n"
        f"Mode: {'Strict (KNOWN_SCAMMER + CRITICAL only)' if strict_mode else 'Full (includes HIGH risk)'}\n"
        "Please wait..."
    )

    try:
        # Get forensics engine and export data
        engine = get_forensics_engine()
        export_data = engine.export_scammer_database_json(
            min_confidence=0.8 if strict_mode else 0.7
        )

        # If strict mode, filter to only KNOWN_SCAMMER and CRITICAL
        if strict_mode:
            export_data["scammers"] = [
                s for s in export_data["scammers"]
                if s["risk_level"] in ("KNOWN_SCAMMER", "CRITICAL")
            ]
            # Update stats
            export_data["stats"]["total_entries"] = len(export_data["scammers"])
            export_data["stats"]["high_risk"] = 0

        # Convert to JSON
        json_content = json.dumps(export_data, indent=2, default=str)
        json_bytes = json_content.encode("utf-8")

        # Generate filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"ai_sentinel_scammers_{timestamp}.json"

        # Send as file
        file = BufferedInputFile(json_bytes, filename=filename)

        stats = export_data["stats"]
        caption = (
            f"🛡️ <b>AI Sentinel Scammer Database</b>\n\n"
            f"📊 <b>Statistics:</b>\n"
            f"• Total entries: {stats['total_entries']}\n"
            f"• Known scammers: {stats['known_scammers']}\n"
            f"• Critical risk: {stats['critical_risk']}\n"
            f"• High risk: {stats['high_risk']}\n\n"
            f"📅 Generated: {export_data['generated_at']}\n"
            f"🔒 Confidence threshold: {export_data['methodology']['confidence_threshold']}\n\n"
            f"<i>This data is free to use. Attribution appreciated.</i>"
        )

        await msg.answer_document(file, caption=caption)
        logger.info(f"Scammer database exported by user {msg.from_user.id}: {stats['total_entries']} entries")

    except Exception as e:
        logger.error(f"Error exporting scammer database: {e}")
        await msg.answer(
            "❌ <b>Export Failed</b>\n\n"
            f"Error: {str(e)[:200]}\n\n"
            "Please try again later or contact support."
        )


@router.message(Command("add_scammer"))
async def cmd_add_scammer(msg: Message):
    """
    Handle /add_scammer command.

    Manually add a wallet to the known scammers list.
    Admin-only command.

    Usage:
        /add_scammer <wallet_address>
    """
    # Check admin permission
    if not is_admin(msg.from_user.id):
        await msg.answer(
            "⛔ <b>Access Denied</b>\n\n"
            "This command is restricted to administrators."
        )
        return

    # Parse wallet address
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer(
            "⚠️ <b>Usage:</b> /add_scammer <wallet_address>\n\n"
            "Example:\n"
            "<code>/add_scammer ABC123...</code>"
        )
        return

    wallet_address = args[1]

    # Basic validation (Solana addresses are 32-44 chars)
    if len(wallet_address) < 32 or len(wallet_address) > 44:
        await msg.answer(
            "❌ <b>Invalid Address</b>\n\n"
            "Please provide a valid Solana wallet address (32-44 characters)."
        )
        return

    try:
        engine = get_forensics_engine()
        engine.add_known_scammer(wallet_address)

        await msg.answer(
            f"✅ <b>Scammer Added</b>\n\n"
            f"Wallet: <code>{wallet_address}</code>\n\n"
            f"This wallet will now be flagged as KNOWN_SCAMMER in all analyses."
        )
        logger.info(f"Scammer added by {msg.from_user.id}: {wallet_address}")

    except Exception as e:
        logger.error(f"Error adding scammer: {e}")
        await msg.answer(f"❌ Error: {str(e)[:200]}")


@router.message(Command("scammer_stats"))
async def cmd_scammer_stats(msg: Message):
    """
    Handle /scammer_stats command.

    Shows statistics about the scammer database.
    """
    try:
        engine = get_forensics_engine()
        export_data = engine.export_scammer_database_json(min_confidence=0.7)
        stats = export_data["stats"]

        stats_text = (
            "🛡️ <b>Scammer Database Statistics</b>\n\n"
            f"📊 <b>Total Tracked:</b> {stats['total_entries']} wallets\n\n"
            f"<b>By Risk Level:</b>\n"
            f"• 🔴 Known Scammers: {stats['known_scammers']}\n"
            f"• 🟠 Critical Risk: {stats['critical_risk']}\n"
            f"• 🟡 High Risk: {stats['high_risk']}\n\n"
            f"<i>Use /export_scammers to download the full database</i>"
        )

        await msg.answer(stats_text)

    except Exception as e:
        logger.error(f"Error getting scammer stats: {e}")
        await msg.answer(f"❌ Error: {str(e)[:200]}")
