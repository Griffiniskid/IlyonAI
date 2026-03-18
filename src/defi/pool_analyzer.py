"""
DeFi Pool Analyzer.

Fetches and analyzes liquidity pool data from DefiLlama, DexScreener,
and on-chain sources. Provides TVL, volume, APR, and risk assessment.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from src.data.defillama import DefiLlamaClient
from src.defi.opportunity_taxonomy import PHASE_1_CHAINS, normalize_chain_name

logger = logging.getLogger(__name__)


def _pool_value(pool: Dict[str, Any], snake_key: str, legacy_key: Optional[str] = None, default: Any = None) -> Any:
    if snake_key in pool and pool.get(snake_key) is not None:
        return pool.get(snake_key)
    if legacy_key and legacy_key in pool and pool.get(legacy_key) is not None:
        return pool.get(legacy_key)
    return default


class PoolAnalyzer:
    """
    Fetches and analyzes DeFi liquidity pools across chains.

    Data sources:
    - DefiLlama: authoritative TVL + pool yields
    - DexScreener: 24h volume, price impact
    """

    SUPPORTED_CHAINS = PHASE_1_CHAINS

    @classmethod
    def normalize_chain_name(cls, chain: Any) -> Optional[str]:
        return normalize_chain_name(chain)

    def __init__(self):
        self._llama = DefiLlamaClient()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    # ------------------------------------------------------------------
    # Pool risk scoring
    # ------------------------------------------------------------------

    def _score_pool_risk(self, pool: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score a pool 0-100 for risk (higher = riskier).

        Factors:
        - Low TVL (< $100k) → high risk
        - New pool (< 30 days old) → elevated risk
        - Extremely high APY (> 500%) → likely unsustainable / honeypot farm
        - Single-sided exposure
        - Audited protocol → lower risk
        """
        risk_score = 30
        risk_flags = []

        tvl = _pool_value(pool, "tvl_usd", "tvlUsd", 0) or 0
        apy = _pool_value(pool, "apy", default=0) or 0
        il_risk = _pool_value(pool, "il_risk", "ilRisk", "")
        audits = _pool_value(pool, "audits", default=0) or 0
        age_days = _pool_value(pool, "age_days", "ageDays", 0) or 0

        # TVL checks
        if tvl < 10_000:
            risk_score += 40
            risk_flags.append("Extremely low TVL (< $10k) — very high slippage risk")
        elif tvl < 100_000:
            risk_score += 25
            risk_flags.append("Low TVL (< $100k) — high slippage risk")
        elif tvl < 1_000_000:
            risk_score += 10
            risk_flags.append("Moderate TVL (< $1M)")

        # APY sustainability
        if apy > 1000:
            risk_score += 30
            risk_flags.append(f"Unsustainably high APY ({apy:.0f}%) — likely inflationary or farm-and-dump")
        elif apy > 500:
            risk_score += 15
            risk_flags.append(f"Very high APY ({apy:.0f}%) — verify emissions sustainability")
        elif apy > 200:
            risk_score += 5
            risk_flags.append(f"High APY ({apy:.0f}%) — monitor for rapid decline")

        # Impermanent loss
        if il_risk and il_risk.lower() == "yes":
            risk_score += 10
            risk_flags.append("Significant impermanent loss risk")

        # Audit status
        if audits and int(audits) > 0:
            risk_score -= 10

        # Age
        if age_days and age_days < 7:
            risk_score += 20
            risk_flags.append(f"Very new pool ({age_days:.0f} days old)")
        elif age_days and age_days < 30:
            risk_score += 10
            risk_flags.append(f"Relatively new pool ({age_days:.0f} days old)")

        risk_score = max(0, min(100, risk_score))

        if risk_score >= 70:
            risk_level = "HIGH"
        elif risk_score >= 45:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            **pool,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_flags": risk_flags,
        }

    # ------------------------------------------------------------------
    # Fetch + filter
    # ------------------------------------------------------------------

    async def get_top_pools(
        self,
        chain: Optional[str] = None,
        protocol: Optional[str] = None,
        min_tvl: float = 100_000,
        max_apy: Optional[float] = None,
        min_apy: Optional[float] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch top pools filtered by chain, protocol, TVL, and APY.

        Returns scored pool objects sorted by TVL descending.
        """
        normalized_chain = self.normalize_chain_name(chain)
        if chain is not None and normalized_chain is None:
            return []

        try:
            raw_pools = await self._llama.get_pools()
        except Exception as e:
            logger.error(f"DefiLlama pools fetch failed: {e}")
            raw_pools = []

        # Apply filters
        filtered = []
        for pool in raw_pools:
            if not bool(pool.get("is_lp_like")):
                continue
            if bool(pool.get("is_incentivized")):
                continue
            pool_tvl = _pool_value(pool, "tvl_usd", "tvlUsd", 0) or 0
            pool_apy = _pool_value(pool, "apy", default=0) or 0
            pool_chain = self.normalize_chain_name(_pool_value(pool, "chain", default=""))
            pool_project = (_pool_value(pool, "project", default="") or "").lower()

            if pool_tvl < min_tvl:
                continue
            if pool_chain is None:
                continue
            if normalized_chain and pool_chain != normalized_chain:
                continue
            if protocol and pool_project != protocol.lower():
                continue
            if max_apy is not None and pool_apy > max_apy:
                continue
            if min_apy is not None and pool_apy < min_apy:
                continue

            filtered.append(pool)

        # Sort by TVL desc
        filtered.sort(key=lambda p: _pool_value(p, "tvl_usd", "tvlUsd", 0) or 0, reverse=True)
        filtered = filtered[:limit]

        # Score risk
        scored = [self._score_pool_risk(p) for p in filtered]
        return scored

    async def get_pool_detail(self, pool_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch historical chart data + current info for a specific pool.
        """
        try:
            chart = await self._llama.get_pool_chart(pool_id)
        except Exception as e:
            logger.warning(f"Pool chart fetch failed for {pool_id}: {e}")
            chart = []

        if not chart:
            return None

        # Last data point = current state
        current = chart[-1] if chart else {}
        pool_info = {
            "pool_id": pool_id,
            "apy": current.get("apy"),
            "tvl_usd": current.get("tvlUsd"),
            "tvlUsd": current.get("tvlUsd"),
            "history_7d": chart[-7:] if len(chart) >= 7 else chart,
            "history_30d": chart[-30:] if len(chart) >= 30 else chart,
        }
        return self._score_pool_risk(pool_info)

    async def close(self):
        await self._llama.close()
        if self._session and not self._session.closed:
            await self._session.close()
