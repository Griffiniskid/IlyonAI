"""
DeFi Yield Farm Analyzer.

Analyzes yield farming opportunities from DefiLlama pools,
classifies them by risk tier, and provides AI-assisted
sustainability assessment for high-APY opportunities.
"""

import logging
from typing import Any, Dict, List, Optional

from src.data.defillama import DefiLlamaClient
from src.defi.opportunity_taxonomy import PHASE_1_CHAINS, normalize_chain_name

logger = logging.getLogger(__name__)


def _pool_value(pool: Dict[str, Any], snake_key: str, legacy_key: Optional[str] = None, default: Any = None) -> Any:
    if snake_key in pool and pool.get(snake_key) is not None:
        return pool.get(snake_key)
    if legacy_key and legacy_key in pool and pool.get(legacy_key) is not None:
        return pool.get(legacy_key)
    return default


# APY tiers for classification
APY_TIERS = {
    "stable":     (0, 20),     # Stable / sustainable
    "moderate":   (20, 100),   # Moderate yield
    "high":       (100, 500),  # High — verify emissions
    "extreme":    (500, None),  # Extreme — likely unsustainable
}


def classify_apy(apy: float) -> str:
    """Classify an APY value into a named tier."""
    if apy < 20:
        return "stable"
    elif apy < 100:
        return "moderate"
    elif apy < 500:
        return "high"
    else:
        return "extreme"


def _exposure_type(pool: Dict[str, Any]) -> str:
    """Determine pool exposure type from symbol."""
    symbol = pool.get("symbol", "")
    stable_tokens = {"USDC", "USDT", "DAI", "FRAX", "BUSD", "LUSD", "sUSD", "TUSD", "USDP"}
    parts = [p.strip() for p in symbol.replace("-", "/").split("/")]
    if all(p in stable_tokens for p in parts if p):
        return "stable-stable"
    elif any(p in stable_tokens for p in parts if p):
        return "crypto-stable"
    else:
        return "crypto-crypto"


class FarmAnalyzer:
    """
    Analyzes yield farming opportunities.

    Provides:
    - Filtered + ranked yield opportunities
    - Sustainability assessment (emissions vs fees)
    - Risk-adjusted return estimates
    """

    SUPPORTED_CHAINS = PHASE_1_CHAINS

    @classmethod
    def normalize_chain_name(cls, chain: Any) -> Optional[str]:
        return normalize_chain_name(chain)

    def __init__(self):
        self._llama = DefiLlamaClient()

    def _score_yield(self, pool: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce a risk-adjusted yield score and structured summary.
        """
        apy = _pool_value(pool, "apy", default=0) or 0
        tvl = _pool_value(pool, "tvl_usd", "tvlUsd", 0) or 0
        apy_base = _pool_value(pool, "apy_base", "apyBase", 0) or 0
        apy_reward = _pool_value(pool, "apy_reward", "apyReward", 0) or 0
        il_risk = str(_pool_value(pool, "il_risk", "ilRisk", "")).lower() == "yes"

        exposure = _exposure_type(pool)
        apy_tier = classify_apy(apy)

        # Sustainability ratio: how much comes from real fees vs emissions
        sustainability_ratio = (apy_base / apy) if apy > 0 else 0

        risk_score = 20
        risk_flags = []

        if tvl < 50_000:
            risk_score += 35
            risk_flags.append("Very low TVL — high slippage and exit risk")
        elif tvl < 500_000:
            risk_score += 15
            risk_flags.append("Low TVL — moderate liquidity risk")

        if apy_tier == "extreme":
            risk_score += 35
            risk_flags.append(f"Extreme APY ({apy:.0f}%) — almost certainly inflationary; farm-and-dump likely")
        elif apy_tier == "high":
            risk_score += 15
            risk_flags.append(f"High APY ({apy:.0f}%) — verify token emission schedule")

        if sustainability_ratio < 0.1 and apy > 20:
            risk_score += 15
            risk_flags.append(
                f"Only {sustainability_ratio*100:.1f}% of yield from real fees — "
                "heavily emission-dependent; APY will collapse when farming ends"
            )

        if il_risk and exposure == "crypto-crypto":
            risk_score += 15
            risk_flags.append("High impermanent loss risk (volatile pair)")
        elif il_risk and exposure == "crypto-stable":
            risk_score += 8
            risk_flags.append("Moderate impermanent loss risk (mixed pair)")

        risk_score = max(0, min(100, risk_score))

        if risk_score >= 70:
            risk_level = "HIGH"
        elif risk_score >= 45:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            **pool,
            "apy_tier": apy_tier,
            "exposure_type": exposure,
            "apy_base": apy_base,
            "apy_reward": apy_reward,
            "sustainability_ratio": round(sustainability_ratio, 3),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_flags": risk_flags,
        }

    async def get_yields(
        self,
        chain: Optional[str] = None,
        exposure: Optional[str] = None,   # stable-stable | crypto-stable | crypto-crypto
        min_apy: float = 1.0,
        max_apy: Optional[float] = None,
        min_tvl: float = 50_000,
        min_sustainability: float = 0.0,  # 0-1, fraction of APY from real fees
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch and filter yield farming opportunities.
        """
        normalized_chain = self.normalize_chain_name(chain)
        if chain is not None and normalized_chain is None:
            return []

        try:
            raw = await self._llama.get_pools()
        except Exception as e:
            logger.error(f"Failed to fetch pools for yield analysis: {e}")
            return []

        results = []
        for pool in raw:
            if not bool(pool.get("is_lp_like")):
                continue
            if not bool(pool.get("is_incentivized")):
                continue
            pool_apy = _pool_value(pool, "apy", default=0) or 0
            pool_tvl = _pool_value(pool, "tvl_usd", "tvlUsd", 0) or 0
            pool_chain = self.normalize_chain_name(_pool_value(pool, "chain", default=""))

            if pool_apy < min_apy:
                continue
            if pool_tvl < min_tvl:
                continue
            if pool_chain is None:
                continue
            if normalized_chain and pool_chain != normalized_chain:
                continue
            if max_apy is not None and pool_apy > max_apy:
                continue

            scored = self._score_yield(pool)

            if exposure and scored["exposure_type"] != exposure:
                continue
            if min_sustainability > 0 and scored["sustainability_ratio"] < min_sustainability:
                continue

            results.append(scored)

        # Sort by APY descending (after filtering)
        results.sort(key=lambda p: p.get("apy") or 0, reverse=True)
        return results[:limit]

    async def close(self):
        await self._llama.close()
