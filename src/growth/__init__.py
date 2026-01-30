"""
Growth module for AI Sentinel.

Provides viral growth features:
- Referral system
- Share tracking
- Leaderboards
"""

from src.growth.referral import ReferralManager, get_referral_manager

__all__ = [
    "ReferralManager",
    "get_referral_manager",
]
