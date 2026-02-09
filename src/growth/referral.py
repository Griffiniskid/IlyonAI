"""
Referral system for Ilyon AI viral growth.

Handles:
- Referral code generation and tracking
- Deep link processing (/start ref_{code})
- Referral statistics and leaderboards
- Share tracking for viral loops
"""

import logging
from typing import Optional, Dict, Any, List

from src.storage.database import get_database

logger = logging.getLogger(__name__)


class ReferralManager:
    """
    Manages referral codes, tracking, and rewards.

    Implements viral growth mechanics:
    - Each user gets a unique referral code
    - Referrals tracked when new users join via deep link
    - Leaderboard shows top referrers
    """

    BOT_USERNAME = "IlyonAIBot"  # Update with actual bot username

    def __init__(self):
        """Initialize referral manager"""
        self._db = None

    async def _get_db(self):
        """Get database instance lazily"""
        if self._db is None:
            self._db = await get_database()
        return self._db

    # ═══════════════════════════════════════════════════════════════════════════
    # REFERRAL LINKS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_referral_link(self, telegram_id: int) -> str:
        """
        Get user's referral link.

        Args:
            telegram_id: User's Telegram ID

        Returns:
            Telegram deep link for referral
        """
        db = await self._get_db()
        user = await db.get_user(telegram_id)

        if user and user.referral_code:
            return f"https://t.me/{self.BOT_USERNAME}?start=ref_{user.referral_code}"

        # Fallback if no user/code
        return f"https://t.me/{self.BOT_USERNAME}"

    async def get_referral_code(self, telegram_id: int) -> Optional[str]:
        """
        Get user's referral code.

        Args:
            telegram_id: User's Telegram ID

        Returns:
            Referral code or None
        """
        db = await self._get_db()
        user = await db.get_user(telegram_id)
        return user.referral_code if user else None

    # ═══════════════════════════════════════════════════════════════════════════
    # DEEP LINK PROCESSING
    # ═══════════════════════════════════════════════════════════════════════════

    async def process_start_parameter(
        self,
        new_user_telegram_id: int,
        start_param: str
    ) -> Dict[str, Any]:
        """
        Process /start deep link parameter.

        Handles:
        - ref_{code} - Referral tracking
        - Token addresses - Direct analysis
        - Other parameters

        Args:
            new_user_telegram_id: New user's Telegram ID
            start_param: The parameter after /start

        Returns:
            Dict with processing result:
            {
                "type": "referral" | "token" | "unknown",
                "referrer_id": int (if referral),
                "token_address": str (if token),
                "success": bool
            }
        """
        result = {
            "type": "unknown",
            "success": False
        }

        # Check for referral code
        if start_param.startswith("ref_"):
            ref_code = start_param[4:]  # Remove "ref_" prefix
            return await self._process_referral(new_user_telegram_id, ref_code)

        # Check if it looks like a Solana address (32-44 base58 chars)
        if len(start_param) >= 32 and len(start_param) <= 44:
            result["type"] = "token"
            result["token_address"] = start_param
            result["success"] = True
            return result

        return result

    async def _process_referral(
        self,
        new_user_telegram_id: int,
        ref_code: str
    ) -> Dict[str, Any]:
        """
        Process referral code.

        Args:
            new_user_telegram_id: New user's Telegram ID
            ref_code: Referral code (without ref_ prefix)

        Returns:
            Result dict with referrer info
        """
        result = {
            "type": "referral",
            "success": False,
            "referrer_id": None,
            "already_referred": False
        }

        db = await self._get_db()

        # Get referrer by code
        referrer = await db.get_user_by_referral_code(ref_code)
        if not referrer:
            logger.warning(f"Invalid referral code: {ref_code}")
            return result

        # Don't allow self-referral
        if referrer.telegram_id == new_user_telegram_id:
            logger.warning(f"Self-referral attempted: {new_user_telegram_id}")
            return result

        # Check if already referred
        new_user = await db.get_user(new_user_telegram_id)
        if new_user and new_user.referred_by_id:
            result["already_referred"] = True
            return result

        # Track the referral
        success = await db.track_referral(ref_code, new_user_telegram_id)

        if success:
            result["success"] = True
            result["referrer_id"] = referrer.telegram_id
            result["referrer_name"] = referrer.first_name or referrer.username
            logger.info(f"Referral tracked: {referrer.telegram_id} -> {new_user_telegram_id}")

        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_user_referral_stats(self, telegram_id: int) -> Dict[str, Any]:
        """
        Get referral statistics for a user.

        Args:
            telegram_id: User's Telegram ID

        Returns:
            Dict with referral stats
        """
        db = await self._get_db()
        user = await db.get_user(telegram_id)

        if not user:
            return {
                "referral_code": None,
                "referral_link": None,
                "total_referrals": 0,
                "rank": None
            }

        total_referrals = await db.count_referrals(user.id)
        referral_link = await self.get_referral_link(telegram_id)

        return {
            "referral_code": user.referral_code,
            "referral_link": referral_link,
            "total_referrals": total_referrals,
            "rank": None  # TODO: Calculate rank
        }

    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top referrers leaderboard.

        Args:
            limit: Number of top referrers to return

        Returns:
            List of referrer info dicts
        """
        db = await self._get_db()
        return await db.get_referral_leaderboard(limit)

    # ═══════════════════════════════════════════════════════════════════════════
    # SHARE TRACKING
    # ═══════════════════════════════════════════════════════════════════════════

    async def track_share(self, telegram_id: int) -> bool:
        """
        Track when user shares content (report card, etc.).

        Args:
            telegram_id: User's Telegram ID

        Returns:
            True if tracked
        """
        # TODO: Implement share tracking in database
        logger.debug(f"Share tracked for user {telegram_id}")
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_manager: Optional[ReferralManager] = None


def get_referral_manager() -> ReferralManager:
    """Get or create global referral manager instance"""
    global _manager
    if _manager is None:
        _manager = ReferralManager()
    return _manager
