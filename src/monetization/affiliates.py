"""
Trojan Bot affiliate link generation.

This module handles Trojan Bot affiliate links for quick-buy functionality.
Simplified from multi-bot system to Trojan-only per production requirements.
"""

import logging
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# TROJAN BOT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

TROJAN_BOT_URL = "https://t.me/solana_trojanbot"
TROJAN_NAME = "Trojan"
TROJAN_EMOJI = "⚡"
TROJAN_COMMISSION = "25-35%"


# ═══════════════════════════════════════════════════════════════════════════════
# LINK GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def get_trojan_link(token_address: str) -> str:
    """
    Generate Trojan Bot affiliate link with token address.

    Args:
        token_address: Solana token address

    Returns:
        Formatted Trojan affiliate link for quick buy
    """
    return settings.get_trojan_link(token_address)


def get_trojan_ref_link() -> str:
    """
    Get Trojan Bot referral link without token.

    Returns:
        Trojan affiliate base link
    """
    return settings.get_trojan_ref_link()


def get_primary_buy_link(token_address: str) -> str:
    """
    Get primary buy link (Trojan Bot).

    Args:
        token_address: Solana token address

    Returns:
        Trojan affiliate link
    """
    return get_trojan_link(token_address)


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════════════════

class AffiliateManager:
    """
    Legacy compatibility wrapper.

    Provides same interface as old multi-bot system but only uses Trojan.
    """

    def __init__(self):
        """Initialize affiliate manager"""
        logger.info(f"✅ AffiliateManager initialized (Trojan Bot only)")

    def get_primary_bot(self):
        """Get primary bot info (Trojan)"""
        return type('Bot', (), {
            'key': 'trojan',
            'name': TROJAN_NAME,
            'emoji': TROJAN_EMOJI,
            'commission': TROJAN_COMMISSION,
            'bot_url': TROJAN_BOT_URL
        })()

    def get_primary_buy_link(self, token_address: str) -> str:
        """Get primary buy link"""
        return get_trojan_link(token_address)

    def get_primary_ref_link(self) -> str:
        """Get primary referral link"""
        return get_trojan_ref_link()

    @property
    def enabled_bots(self):
        """Get list of enabled bots (just Trojan)"""
        return [self.get_primary_bot()]


# Global manager instance
_manager: Optional[AffiliateManager] = None


def get_manager() -> AffiliateManager:
    """Get or create global AffiliateManager instance"""
    global _manager
    if _manager is None:
        _manager = AffiliateManager()
    return _manager
