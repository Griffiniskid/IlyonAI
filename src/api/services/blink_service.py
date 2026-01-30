"""
Business logic for Solana Blinks operations.

Handles creating, retrieving, and executing Blinks for
shareable token security analysis.
"""

import base64
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

from src.config import settings
from src.storage.database import get_database

logger = logging.getLogger(__name__)


class BlinkService:
    """
    Service for managing Solana Blinks.

    Provides methods for creating shareable links, retrieving metadata
    for Twitter unfurling, and executing verification actions.
    """

    def __init__(self):
        self.base_url = settings.actions_base_url

    def _generate_id(self, token_address: str) -> str:
        """
        Generate URL-safe unique blink ID.

        Uses hash of token address + timestamp for uniqueness.

        Args:
            token_address: Solana token address

        Returns:
            8-character URL-safe ID
        """
        data = f"{token_address}:{datetime.utcnow().timestamp()}"
        hash_bytes = hashlib.sha256(data.encode()).digest()[:6]
        return base64.urlsafe_b64encode(hash_bytes).decode().rstrip("=")

    def _serialize_result(self, result) -> Dict[str, Any]:
        """
        Serialize AnalysisResult for storage.

        Args:
            result: AnalysisResult from analyzer

        Returns:
            Dictionary with serialized data
        """
        t = result.token
        return {
            "overall_score": result.overall_score,
            "grade": result.grade,
            "safety_score": getattr(result, "safety_score", None),
            "liquidity_score": getattr(result, "liquidity_score", None),
            "social_score": getattr(result, "social_score", None),
            "token": {
                "address": t.address,
                "symbol": t.symbol,
                "name": t.name,
                "price_usd": getattr(t, "price_usd", None),
                "liquidity_usd": getattr(t, "liquidity_usd", None),
                "ai_verdict": getattr(t, "ai_verdict", None),
                "ai_rug_probability": getattr(t, "ai_rug_probability", None),
                "liquidity_locked": getattr(t, "liquidity_locked", None),
            },
        }

    def _build_description(self, blink) -> str:
        """
        Build description string for Solana Actions metadata.

        Args:
            blink: Blink database object

        Returns:
            Formatted description string
        """
        parts = []

        if blink.overall_score is not None:
            parts.append(f"Score: {blink.overall_score}/100 ({blink.grade or '?'})")

        if blink.ai_verdict:
            parts.append(f"Verdict: {blink.ai_verdict}")

        if blink.liquidity_locked is not None:
            parts.append("LP Locked" if blink.liquidity_locked else "LP NOT LOCKED")

        if blink.ai_rug_probability is not None:
            parts.append(f"Rug Risk: {blink.ai_rug_probability}%")

        return " | ".join(parts) if parts else "Token Security Analysis"

    async def create_blink(
        self,
        token_address: str,
        analysis_result,
        telegram_id: int,
    ) -> Dict[str, str]:
        """
        Create a new shareable Blink from analysis result.

        Args:
            token_address: Solana token address
            analysis_result: AnalysisResult from analyzer
            telegram_id: Creator's Telegram ID

        Returns:
            Dictionary with blink ID and URL
        """
        db = await get_database()

        # Check if recent blink exists for this token
        existing = await db.get_blink_by_token(token_address)
        if existing:
            # Update with fresh result
            await db.update_blink_result(
                blink_id=existing.id,
                overall_score=analysis_result.overall_score,
                grade=analysis_result.grade,
                ai_verdict=getattr(analysis_result.token, "ai_verdict", None),
                ai_rug_probability=getattr(analysis_result.token, "ai_rug_probability", None),
                liquidity_locked=getattr(analysis_result.token, "liquidity_locked", None),
                cached_result=self._serialize_result(analysis_result),
            )
            logger.info(f"Updated existing blink {existing.id} for {token_address[:16]}...")
            return {
                "id": existing.id,
                "url": f"{self.base_url}/blinks/{existing.id}",
            }

        # Generate new blink ID
        blink_id = self._generate_id(token_address)

        # Calculate expiration
        expires_at = None
        if settings.blink_ttl_hours > 0:
            expires_at = datetime.utcnow() + timedelta(hours=settings.blink_ttl_hours)

        # Create blink
        t = analysis_result.token
        await db.create_blink(
            blink_id=blink_id,
            token_address=token_address,
            token_symbol=getattr(t, "symbol", None),
            token_name=getattr(t, "name", None),
            overall_score=analysis_result.overall_score,
            grade=analysis_result.grade,
            ai_verdict=getattr(t, "ai_verdict", None),
            ai_rug_probability=getattr(t, "ai_rug_probability", None),
            liquidity_locked=getattr(t, "liquidity_locked", None),
            cached_result=self._serialize_result(analysis_result),
            created_by_telegram_id=telegram_id,
            expires_at=expires_at,
        )

        return {
            "id": blink_id,
            "url": f"{self.base_url}/blinks/{blink_id}",
        }

    async def get_blink(self, blink_id: str):
        """
        Get a Blink by ID.

        Args:
            blink_id: Blink identifier

        Returns:
            Blink object or None
        """
        db = await get_database()
        return await db.get_blink(blink_id)

    async def get_metadata(self, blink_id: str) -> Dict[str, Any]:
        """
        Get Solana Actions metadata for Twitter unfurling.

        Args:
            blink_id: Blink identifier

        Returns:
            Solana Actions metadata dictionary

        Raises:
            ValueError: If blink not found
        """
        db = await get_database()
        blink = await db.get_blink(blink_id)

        if not blink:
            raise ValueError("Blink not found")

        # Check expiration
        if blink.expires_at and blink.expires_at < datetime.utcnow():
            raise ValueError("Blink has expired")

        # Build title
        symbol = blink.token_symbol or "Token"
        title = f"${symbol} Security Analysis"

        # Build description
        description = self._build_description(blink)

        return {
            "type": "action",
            "icon": f"{self.base_url}/api/v1/blinks/{blink_id}/icon.png",
            "title": title,
            "description": description,
            "label": "Verify Token",
            "links": {
                "actions": [
                    {
                        "label": "Verify Token",
                        "href": f"/api/v1/blinks/{blink_id}",
                    }
                ]
            },
        }

    async def execute_verify(
        self,
        blink_id: str,
        body: Dict[str, Any],
        ip_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute the verify action - run fresh quick analysis.

        Args:
            blink_id: Blink identifier
            body: Request body from Actions client
            ip_hash: Hashed IP for analytics

        Returns:
            Action result message

        Raises:
            ValueError: If blink not found
        """
        db = await get_database()
        blink = await db.get_blink(blink_id)

        if not blink:
            raise ValueError("Blink not found")

        # Run fresh quick analysis
        try:
            from src.core.analyzer import TokenAnalyzer

            analyzer = TokenAnalyzer()
            result = await analyzer.analyze(blink.token_address, mode="quick")

            if not result:
                return {
                    "type": "message",
                    "message": f"Unable to analyze ${blink.token_symbol or 'token'}. Please try again later.",
                }

            # Update blink with fresh result
            t = result.token
            await db.update_blink_result(
                blink_id=blink_id,
                overall_score=result.overall_score,
                grade=result.grade,
                ai_verdict=getattr(t, "ai_verdict", None),
                ai_rug_probability=getattr(t, "ai_rug_probability", None),
                liquidity_locked=getattr(t, "liquidity_locked", None),
                cached_result=self._serialize_result(result),
            )

            # Increment verification count
            await db.increment_blink_verifications(blink_id)

            # Format response message
            symbol = getattr(t, "symbol", blink.token_symbol) or "Token"
            verdict = getattr(t, "ai_verdict", "UNKNOWN")
            rug_prob = getattr(t, "ai_rug_probability", "?")
            lp_status = "Locked" if getattr(t, "liquidity_locked", False) else "NOT LOCKED"

            message = (
                f"Fresh Analysis for ${symbol}\n\n"
                f"Score: {result.overall_score}/100 ({result.grade})\n"
                f"Verdict: {verdict}\n"
                f"Rug Probability: {rug_prob}%\n"
                f"LP: {lp_status}\n\n"
                f"Full report: https://t.me/aisentinelbot?start=check_{blink.token_address[:16]}"
            )

            logger.info(f"Verification executed for blink {blink_id}: score={result.overall_score}")

            return {
                "type": "message",
                "message": message,
            }

        except Exception as e:
            logger.error(f"Error executing verification for {blink_id}: {e}")
            return {
                "type": "message",
                "message": f"Error verifying token. Please try again later.\n\nError: {str(e)[:100]}",
            }

    async def track_event(
        self,
        blink_id: str,
        event_type: str,
        ip_hash: Optional[str] = None,
        user_agent: Optional[str] = None,
        referrer: Optional[str] = None,
    ) -> bool:
        """
        Track a blink analytics event.

        Args:
            blink_id: Blink identifier
            event_type: Event type ('view', 'verify', 'share')
            ip_hash: Hashed IP address
            user_agent: Request user agent
            referrer: Request referrer URL

        Returns:
            True if tracked successfully
        """
        db = await get_database()

        # Increment appropriate counter
        if event_type == "view":
            await db.increment_blink_views(blink_id)
        elif event_type == "verify":
            await db.increment_blink_verifications(blink_id)

        # Track detailed event
        return await db.track_blink_event(
            blink_id=blink_id,
            event_type=event_type,
            ip_hash=ip_hash,
            user_agent=user_agent,
            referrer=referrer,
        )


# Global service instance
_blink_service: Optional[BlinkService] = None


def get_blink_service() -> BlinkService:
    """Get or create global blink service"""
    global _blink_service
    if _blink_service is None:
        _blink_service = BlinkService()
    return _blink_service
