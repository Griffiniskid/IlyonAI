"""
Time-series data collection for behavioral analysis.

Collects and stores historical snapshots of token metrics
for pattern detection and anomaly analysis.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import asyncio

import aiohttp

logger = logging.getLogger(__name__)


def calculate_repeat_wallet_share(wallets: List[str]) -> float:
    """Share of wallet observations belonging to wallets seen more than once."""
    if not wallets:
        return 0.0

    counts: Dict[str, int] = {}
    for wallet in wallets:
        if not wallet:
            continue
        counts[wallet] = counts.get(wallet, 0) + 1

    repeated_observations = sum(count for count in counts.values() if count > 1)
    total_observations = sum(counts.values())
    return repeated_observations / total_observations if total_observations else 0.0


@dataclass
class TimeSeriesDataPoint:
    """Single data point in token time series."""

    timestamp: datetime
    liquidity_usd: float = 0.0
    volume_1h: float = 0.0
    price_usd: float = 0.0
    market_cap: float = 0.0
    holder_count: int = 0
    top_10_concentration: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    large_sells: int = 0  # Sells > 1% of liquidity
    price_change_1h: float = 0.0
    whale_net_flow_usd: float = 0.0
    repeat_wallet_share: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "liquidity_usd": self.liquidity_usd,
            "volume_1h": self.volume_1h,
            "price_usd": self.price_usd,
            "market_cap": self.market_cap,
            "holder_count": self.holder_count,
            "top_10_concentration": self.top_10_concentration,
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "large_sells": self.large_sells,
            "price_change_1h": self.price_change_1h,
            "whale_net_flow_usd": self.whale_net_flow_usd,
            "repeat_wallet_share": self.repeat_wallet_share,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeSeriesDataPoint":
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            liquidity_usd=data.get("liquidity_usd", 0.0),
            volume_1h=data.get("volume_1h", 0.0),
            price_usd=data.get("price_usd", 0.0),
            market_cap=data.get("market_cap", 0.0),
            holder_count=data.get("holder_count", 0),
            top_10_concentration=data.get("top_10_concentration", 0.0),
            buy_count=data.get("buy_count", 0),
            sell_count=data.get("sell_count", 0),
            large_sells=data.get("large_sells", 0),
            price_change_1h=data.get("price_change_1h", 0.0),
            whale_net_flow_usd=data.get("whale_net_flow_usd", 0.0),
            repeat_wallet_share=data.get("repeat_wallet_share", 0.0),
        )


class TimeSeriesStore:
    """Small in-memory store for first-layer behavior snapshots."""

    def __init__(self):
        self._behavior_snapshots: Dict[str, List[Dict[str, Any]]] = {}

    def add_behavior_snapshot(self, token_address: str, snapshot: Dict[str, Any]) -> None:
        snapshots = self._behavior_snapshots.setdefault(token_address, [])
        snapshots.append(snapshot)
        snapshots.sort(key=lambda item: item.get("timestamp") or datetime.min)

    def get_behavior_summary(self, token_address: str) -> Dict[str, Any]:
        snapshots = self._behavior_snapshots.get(token_address, [])
        wallets: List[str] = []
        for snapshot in snapshots:
            wallets.extend([wallet for wallet in snapshot.get("wallets", []) if wallet])

        return {
            "snapshot_count": len(snapshots),
            "repeat_wallet_share": calculate_repeat_wallet_share(wallets),
        }


class TimeSeriesCollector:
    """
    Collects time-series data for token behavioral analysis.

    Uses DexScreener API and caches results for efficiency.
    """

    DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"

    # Cache for time-series data (token_address -> list of data points)
    _cache: Dict[str, List[TimeSeriesDataPoint]] = {}
    _cache_timestamps: Dict[str, datetime] = {}
    CACHE_TTL_MINUTES = 5

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize collector.

        Args:
            session: Optional aiohttp session for reuse
        """
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close session if owned."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def collect_current_snapshot(
        self,
        token_address: str,
    ) -> Optional[TimeSeriesDataPoint]:
        """
        Collect current token metrics as a time-series data point.

        Args:
            token_address: Solana token mint address

        Returns:
            TimeSeriesDataPoint with current metrics, or None on error
        """
        try:
            session = await self._get_session()

            url = f"{self.DEXSCREENER_BASE}/tokens/{token_address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"DexScreener API returned {resp.status} for {token_address}")
                    return None

                data = await resp.json()
                pairs = data.get("pairs", [])

                if not pairs:
                    logger.warning(f"No pairs found for token {token_address}")
                    return None

                # Get the highest liquidity Solana pair
                solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]
                if not solana_pairs:
                    return None

                pair = max(solana_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))

                # Extract metrics
                txns = pair.get("txns", {})
                h1 = txns.get("h1", {})
                h24 = txns.get("h24", {})

                buys_1h = h1.get("buys", 0)
                sells_1h = h1.get("sells", 0)

                liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                volume_1h = float(pair.get("volume", {}).get("h1", 0) or 0)

                # Estimate large sells (sells that are > 1% of liquidity)
                # This is an approximation - real implementation would analyze transactions
                large_sell_threshold = liquidity_usd * 0.01
                estimated_large_sells = 0
                if sells_1h > 0 and volume_1h > 0:
                    avg_sell_size = (volume_1h * (sells_1h / (buys_1h + sells_1h + 1))) / max(sells_1h, 1)
                    if avg_sell_size > large_sell_threshold:
                        estimated_large_sells = max(1, sells_1h // 3)

                return TimeSeriesDataPoint(
                    timestamp=datetime.utcnow(),
                    liquidity_usd=liquidity_usd,
                    volume_1h=volume_1h,
                    price_usd=float(pair.get("priceUsd", 0) or 0),
                    market_cap=float(pair.get("marketCap", 0) or 0),
                    holder_count=0,  # Would need separate RPC call
                    top_10_concentration=0.0,  # Would need holder analysis
                    buy_count=buys_1h,
                    sell_count=sells_1h,
                    large_sells=estimated_large_sells,
                    price_change_1h=float(pair.get("priceChange", {}).get("h1", 0) or 0),
                )

        except asyncio.TimeoutError:
            logger.warning(f"Timeout collecting time-series for {token_address}")
            return None
        except Exception as e:
            logger.error(f"Error collecting time-series for {token_address}: {e}")
            return None

    async def get_historical_data(
        self,
        token_address: str,
        lookback_hours: int = 72,
    ) -> List[TimeSeriesDataPoint]:
        """
        Get historical time-series data for a token.

        Note: DexScreener doesn't provide historical data directly,
        so this returns cached snapshots plus current data.
        For production, this would integrate with a historical data provider.

        Args:
            token_address: Solana token mint address
            lookback_hours: How far back to look (limited by cache)

        Returns:
            List of TimeSeriesDataPoint sorted by timestamp (oldest first)
        """
        # Check cache freshness
        cache_time = self._cache_timestamps.get(token_address)
        if cache_time and (datetime.utcnow() - cache_time).seconds < self.CACHE_TTL_MINUTES * 60:
            cached = self._cache.get(token_address, [])
            if cached:
                return cached

        # Collect current snapshot
        current = await self.collect_current_snapshot(token_address)
        if not current:
            return self._cache.get(token_address, [])

        # Add to cache
        if token_address not in self._cache:
            self._cache[token_address] = []

        # Avoid duplicate timestamps
        existing_timestamps = {p.timestamp.replace(second=0, microsecond=0)
                             for p in self._cache[token_address]}
        current_minute = current.timestamp.replace(second=0, microsecond=0)

        if current_minute not in existing_timestamps:
            self._cache[token_address].append(current)

        # Prune old data beyond lookback
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
        self._cache[token_address] = [
            p for p in self._cache[token_address]
            if p.timestamp > cutoff
        ]

        # Sort by timestamp
        self._cache[token_address].sort(key=lambda p: p.timestamp)
        self._cache_timestamps[token_address] = datetime.utcnow()

        return self._cache[token_address]

    def add_snapshot(self, token_address: str, snapshot: TimeSeriesDataPoint):
        """
        Manually add a snapshot to the cache.

        Useful for integrating with external data sources.
        """
        if token_address not in self._cache:
            self._cache[token_address] = []
        self._cache[token_address].append(snapshot)
        self._cache[token_address].sort(key=lambda p: p.timestamp)

    def get_data_quality_score(self, token_address: str) -> float:
        """
        Calculate data quality score (0-100) based on available history.

        More data points = higher quality for analysis.
        """
        points = self._cache.get(token_address, [])
        if not points:
            return 0.0

        count = len(points)

        # Ideal: 72 hours of hourly data = 72 points
        # Score based on coverage
        if count >= 72:
            return 100.0
        elif count >= 48:
            return 85.0
        elif count >= 24:
            return 70.0
        elif count >= 12:
            return 50.0
        elif count >= 6:
            return 30.0
        else:
            return max(10.0, count * 5)
