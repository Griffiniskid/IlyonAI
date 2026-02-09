"""
Sniper Alert System for Ilyon AI.

Monitors for new token launches and sends alerts to subscribed users.
This is a background service that can be run alongside the main bot.

Features:
- New token launch detection
- Quality filtering (liquidity, socials, security)
- User subscription management
- Telegram notifications
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.data.dexscreener import DexScreenerClient
from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TokenLaunch:
    """Represents a new token launch"""
    address: str
    symbol: str
    name: str
    liquidity_usd: float
    created_at: datetime
    has_website: bool = False
    has_twitter: bool = False
    has_telegram: bool = False
    mint_disabled: bool = False
    lp_locked: bool = False
    score: int = 0


class SniperAlertSystem:
    """
    Monitors for new token launches and sends alerts.

    This system runs as a background task, periodically checking
    for new tokens that meet specified criteria.
    """

    # Alert criteria defaults
    MIN_LIQUIDITY_USD = 5000  # $5k minimum
    MAX_AGE_MINUTES = 60  # Only tokens launched in last hour
    CHECK_INTERVAL_SECONDS = 30  # Check every 30 seconds

    def __init__(
        self,
        callback: Optional[Callable] = None,
        min_liquidity: float = MIN_LIQUIDITY_USD,
        max_age_minutes: int = MAX_AGE_MINUTES
    ):
        """
        Initialize sniper alert system.

        Args:
            callback: Async function to call when alert triggered
            min_liquidity: Minimum liquidity in USD
            max_age_minutes: Maximum age of token in minutes
        """
        self.callback = callback
        self.min_liquidity = min_liquidity
        self.max_age_minutes = max_age_minutes
        self._running = False
        self._seen_tokens: set = set()  # Track seen tokens to avoid duplicates
        self._subscribed_users: set = set()  # User IDs subscribed to alerts

    async def start(self):
        """Start the alert monitoring loop"""
        if self._running:
            logger.warning("Sniper alert system already running")
            return

        self._running = True
        logger.info("🎯 Sniper alert system started")

        while self._running:
            try:
                await self._check_new_launches()
            except Exception as e:
                logger.error(f"Alert check error: {e}")

            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    async def stop(self):
        """Stop the alert monitoring loop"""
        self._running = False
        logger.info("🎯 Sniper alert system stopped")

    def subscribe(self, user_id: int):
        """Subscribe user to alerts"""
        self._subscribed_users.add(user_id)
        logger.info(f"User {user_id} subscribed to sniper alerts")

    def unsubscribe(self, user_id: int):
        """Unsubscribe user from alerts"""
        self._subscribed_users.discard(user_id)
        logger.info(f"User {user_id} unsubscribed from sniper alerts")

    @property
    def subscriber_count(self) -> int:
        """Get number of subscribed users"""
        return len(self._subscribed_users)

    async def _check_new_launches(self):
        """Check for new token launches matching criteria"""
        async with DexScreenerClient() as client:
            # Fetch latest Solana pairs
            url = f"{client.BASE_URL}/latest/dex/pairs/solana"
            data = await client._make_request(url)

            if not data or "pairs" not in data:
                return

            new_launches = []
            cutoff_time = datetime.utcnow() - timedelta(minutes=self.max_age_minutes)

            for pair in data.get("pairs", []):
                try:
                    launch = await self._parse_pair(pair, cutoff_time)
                    if launch and launch.address not in self._seen_tokens:
                        new_launches.append(launch)
                        self._seen_tokens.add(launch.address)
                except Exception as e:
                    logger.debug(f"Error parsing pair: {e}")
                    continue

            # Trigger alerts for qualifying launches
            for launch in new_launches:
                if self._matches_criteria(launch):
                    await self._send_alert(launch)

    async def _parse_pair(
        self,
        pair: Dict[str, Any],
        cutoff_time: datetime
    ) -> Optional[TokenLaunch]:
        """Parse pair data into TokenLaunch"""
        # Check creation time
        created_at_ms = pair.get("pairCreatedAt", 0)
        if not created_at_ms:
            return None

        created_at = datetime.utcfromtimestamp(created_at_ms / 1000)
        if created_at < cutoff_time:
            return None

        # Check liquidity
        liquidity = pair.get("liquidity", {}).get("usd", 0) or 0
        if liquidity < self.min_liquidity:
            return None

        # Extract token info
        base = pair.get("baseToken", {})
        info = pair.get("info", {})
        socials = info.get("socials", [])

        return TokenLaunch(
            address=base.get("address", ""),
            symbol=base.get("symbol", "???"),
            name=base.get("name", "Unknown"),
            liquidity_usd=liquidity,
            created_at=created_at,
            has_website=any(s.get("type") == "website" for s in socials),
            has_twitter=any(s.get("type") == "twitter" for s in socials),
            has_telegram=any(s.get("type") == "telegram" for s in socials),
        )

    def _matches_criteria(self, launch: TokenLaunch) -> bool:
        """Check if launch matches alert criteria"""
        # Basic criteria
        if launch.liquidity_usd < self.min_liquidity:
            return False

        # Score the launch
        score = 0

        # Liquidity score (0-30 points)
        if launch.liquidity_usd >= 50000:
            score += 30
        elif launch.liquidity_usd >= 20000:
            score += 20
        elif launch.liquidity_usd >= 10000:
            score += 15
        else:
            score += 10

        # Social presence (0-30 points)
        if launch.has_website:
            score += 10
        if launch.has_twitter:
            score += 10
        if launch.has_telegram:
            score += 10

        # Security (0-40 points) - would need additional checks
        # For now, skip these

        launch.score = score

        # Only alert if score >= 40 (has some social presence + decent liquidity)
        return score >= 40

    async def _send_alert(self, launch: TokenLaunch):
        """Send alert for new token launch"""
        logger.info(
            f"🚨 New launch alert: ${launch.symbol} "
            f"(Liq: ${launch.liquidity_usd:,.0f}, Score: {launch.score})"
        )

        if self.callback:
            try:
                await self.callback(launch, list(self._subscribed_users))
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

    def format_alert_message(self, launch: TokenLaunch) -> str:
        """Format launch into Telegram message"""
        socials = []
        if launch.has_website:
            socials.append("🌐 Website")
        if launch.has_twitter:
            socials.append("🐦 Twitter")
        if launch.has_telegram:
            socials.append("💬 Telegram")

        social_str = " | ".join(socials) if socials else "❌ No socials"

        age_minutes = (datetime.utcnow() - launch.created_at).total_seconds() / 60

        return f"""
🚨 <b>NEW TOKEN LAUNCH</b>

<b>${launch.symbol}</b> - {launch.name}

💰 <b>Liquidity:</b> ${launch.liquidity_usd:,.0f}
⏱ <b>Age:</b> {int(age_minutes)} minutes
📊 <b>Score:</b> {launch.score}/100

{social_str}

<code>{launch.address}</code>
"""


# Global instance
_alert_system: Optional[SniperAlertSystem] = None


def get_alert_system() -> SniperAlertSystem:
    """Get or create global alert system instance"""
    global _alert_system
    if _alert_system is None:
        _alert_system = SniperAlertSystem()
    return _alert_system
