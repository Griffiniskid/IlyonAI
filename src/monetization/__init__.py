"""
Monetization and affiliate system.

Simplified to Trojan Bot only for production.
"""

from .affiliates import (
    AffiliateManager,
    get_primary_buy_link,
    get_trojan_link,
    get_trojan_ref_link,
    get_manager,
)

__all__ = [
    'AffiliateManager',
    'get_primary_buy_link',
    'get_trojan_link',
    'get_trojan_ref_link',
    'get_manager',
]
