"""
DeFi Lending Protocol Analyzer.

Analyzes lending markets across Aave, Compound, Morpho, Solend,
MarginFi, and Kamino. Provides:
  - Current supply/borrow APY
  - Health factor monitoring
  - Liquidation risk assessment
  - Oracle dependency analysis
  - Cross-protocol rate comparison

Data sourced from: DefiLlama yields API + protocol-specific endpoints.
"""

import logging
from typing import Any, Dict, List, Optional

from src.data.defillama import DefiLlamaClient

logger = logging.getLogger(__name__)

# Known lending protocols and their DefiLlama pool identifiers / categories
LENDING_PROTOCOLS = {
    "aave-v3": {
        "display_name": "Aave V3",
        "chains": ["Ethereum", "Polygon", "Arbitrum", "Optimism", "Avalanche", "Base"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["Trail of Bits", "OpenZeppelin", "PeckShield", "SigmaPrime"],
        "tvl_slug": "aave-v3",
        "docs_url": "https://docs.aave.com",
    },
    "aave-v2": {
        "display_name": "Aave V2",
        "chains": ["Ethereum", "Polygon", "Avalanche"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["Trail of Bits", "OpenZeppelin"],
        "tvl_slug": "aave",
        "docs_url": "https://docs.aave.com",
    },
    "compound-v3": {
        "display_name": "Compound V3",
        "chains": ["Ethereum", "Polygon", "Arbitrum", "Base", "Optimism"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["OpenZeppelin", "ChainSecurity"],
        "tvl_slug": "compound-v3",
        "docs_url": "https://docs.compound.finance",
    },
    "morpho": {
        "display_name": "Morpho Blue",
        "chains": ["Ethereum", "Base"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["Trail of Bits", "Cantina"],
        "tvl_slug": "morpho-blue",
        "docs_url": "https://docs.morpho.org",
    },
    "spark": {
        "display_name": "Spark Protocol",
        "chains": ["Ethereum"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["ChainSecurity"],
        "tvl_slug": "spark",
        "docs_url": "https://docs.spark.fi",
    },
    "solend": {
        "display_name": "Solend",
        "chains": ["Solana"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["Kudelski Security"],
        "tvl_slug": "solend",
        "docs_url": "https://docs.solend.fi",
    },
    "marginfi": {
        "display_name": "MarginFi",
        "chains": ["Solana"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["OtterSec"],
        "tvl_slug": "marginfi",
        "docs_url": "https://docs.marginfi.com",
    },
    "kamino": {
        "display_name": "Kamino Finance",
        "chains": ["Solana"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["OtterSec", "Offside Labs"],
        "tvl_slug": "kamino-lend",
        "docs_url": "https://docs.kamino.finance",
    },
    "euler": {
        "display_name": "Euler V2",
        "chains": ["Ethereum"],
        "category": "Lending",
        "audit_status": "audited",
        "auditors": ["Cantina", "Sherlock"],
        "tvl_slug": "euler-v2",
        "docs_url": "https://docs.euler.finance",
        "incident_note": "Euler V1 was exploited for $197M in March 2023. V2 is a full rewrite.",
    },
}

# Liquidation thresholds per protocol (LTV at which liquidation triggers)
LIQUIDATION_THRESHOLDS = {
    "aave-v3": 0.825,   # varies by asset, 82.5% is typical ETH threshold
    "aave-v2": 0.80,
    "compound-v3": 0.80,
    "morpho": 0.915,    # Morpho uses efficient liquidations
    "spark": 0.83,
    "solend": 0.80,
    "marginfi": 0.80,
    "kamino": 0.80,
    "euler": 0.85,
}


def _pool_value(pool: Dict[str, Any], snake_key: str, legacy_key: Optional[str] = None, default: Any = None) -> Any:
    if snake_key in pool and pool.get(snake_key) is not None:
        return pool.get(snake_key)
    if legacy_key and legacy_key in pool and pool.get(legacy_key) is not None:
        return pool.get(legacy_key)
    return default


class LendingAnalyzer:
    """
    Analyzes lending protocol markets and positions.

    Provides rate comparison, risk assessment, and health factor
    calculation for DeFi lending positions.
    """

    def __init__(self):
        self._llama = DefiLlamaClient()

    # ------------------------------------------------------------------
    # Protocol risk scoring
    # ------------------------------------------------------------------

    def _score_protocol_risk(self, protocol_id: str, tvl: float) -> Dict[str, Any]:
        """Score a lending protocol's systemic risk 0-100 (higher = riskier)."""
        info = LENDING_PROTOCOLS.get(protocol_id, {})
        risk_score = 40
        risk_factors = []

        # Audit status
        if info.get("audit_status") == "audited":
            auditors = info.get("auditors", [])
            if len(auditors) >= 3:
                risk_score -= 20
            elif len(auditors) >= 1:
                risk_score -= 10
        else:
            risk_score += 25
            risk_factors.append("No known security audit")

        # TVL as proxy for battle-testing
        if tvl > 1_000_000_000:      # > $1B
            risk_score -= 15
        elif tvl > 100_000_000:      # > $100M
            risk_score -= 8
        elif tvl < 10_000_000:       # < $10M
            risk_score += 15
            risk_factors.append("Low TVL — limited battle-testing")
        elif tvl < 1_000_000:        # < $1M
            risk_score += 30
            risk_factors.append("Very low TVL — high liquidity risk")

        # Known incidents
        if info.get("incident_note"):
            risk_score += 10
            risk_factors.append(f"Prior incident: {info['incident_note']}")

        risk_score = max(0, min(100, risk_score))

        if risk_score >= 70:
            risk_level = "HIGH"
        elif risk_score >= 45:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
        }

    def _score_market_risk(self, pool: Dict[str, Any]) -> Dict[str, Any]:
        """Score an individual lending market's risk."""
        apy_borrow = _pool_value(pool, "apy_borrow", "apyBorrow", 0) or 0
        tvl = _pool_value(pool, "tvl_usd", "tvlUsd", 0) or 0
        utilization = _pool_value(pool, "utilization", default=0) or 0

        risk_score = 20
        risk_factors = []

        # High utilization = liquidity crunch risk (can't withdraw)
        if utilization > 0.95:
            risk_score += 40
            risk_factors.append(f"Critical utilization ({utilization*100:.0f}%) — withdrawal may fail")
        elif utilization > 0.85:
            risk_score += 20
            risk_factors.append(f"High utilization ({utilization*100:.0f}%) — interest rates volatile")
        elif utilization > 0.70:
            risk_score += 8
            risk_factors.append(f"Elevated utilization ({utilization*100:.0f}%)")

        # Borrow rate — very high rates signal stress
        if apy_borrow > 50:
            risk_score += 25
            risk_factors.append(f"Very high borrow APY ({apy_borrow:.1f}%) — market stress signal")
        elif apy_borrow > 20:
            risk_score += 10
            risk_factors.append(f"High borrow APY ({apy_borrow:.1f}%)")

        # Low TVL in lending = thin liquidity
        if tvl < 1_000_000:
            risk_score += 20
            risk_factors.append("Low market TVL — thin liquidity, large exit impact")

        risk_score = max(0, min(100, risk_score))

        return {
            "risk_score": risk_score,
            "risk_level": "HIGH" if risk_score >= 65 else "MEDIUM" if risk_score >= 40 else "LOW",
            "risk_factors": risk_factors,
        }

    # ------------------------------------------------------------------
    # Health factor calculation
    # ------------------------------------------------------------------

    def calculate_health_factor(
        self,
        collateral_usd: float,
        debt_usd: float,
        protocol: str = "aave-v3",
        collateral_ltv: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculate health factor for a lending position.

        Health factor = (collateral * liquidation_threshold) / debt
        If health factor < 1.0, the position is liquidatable.

        Args:
            collateral_usd: Total collateral value in USD
            debt_usd: Total debt value in USD
            protocol: Protocol slug (for threshold lookup)
            collateral_ltv: Override liquidation threshold (0-1)
        """
        if debt_usd <= 0:
            return {
                "health_factor": float("inf"),
                "status": "SAFE",
                "liquidation_price_drop_pct": None,
                "message": "No debt — position is not at liquidation risk",
            }

        threshold = collateral_ltv or LIQUIDATION_THRESHOLDS.get(protocol, 0.80)
        hf = (collateral_usd * threshold) / debt_usd

        # How much can collateral drop before liquidation?
        # price_at_liquidation = debt / (threshold * initial_collateral_units)
        # drop_pct = 1 - (1/hf)
        drop_pct = max(0, (1 - (1.0 / hf)) * 100) if hf > 0 else 0

        if hf >= 2.0:
            status = "SAFE"
            warning = "Position is well-collateralized."
        elif hf >= 1.5:
            status = "MODERATE"
            warning = f"Position is healthy but monitor. Collateral can drop {drop_pct:.0f}% before liquidation."
        elif hf >= 1.1:
            status = "WARNING"
            warning = f"Position is at moderate risk. Only {drop_pct:.0f}% collateral drop to liquidation."
        else:
            status = "DANGER"
            warning = f"CRITICAL: Position near liquidation. Only {drop_pct:.0f}% buffer remaining."

        return {
            "health_factor": round(hf, 4),
            "status": status,
            "liquidation_threshold": threshold,
            "collateral_usd": collateral_usd,
            "debt_usd": debt_usd,
            "collateral_drop_to_liquidation_pct": round(drop_pct, 2),
            "message": warning,
        }

    # ------------------------------------------------------------------
    # Market fetching
    # ------------------------------------------------------------------

    async def get_lending_markets(
        self,
        protocol: Optional[str] = None,
        chain: Optional[str] = None,
        asset: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch lending markets from DefiLlama, filtered and scored.

        Returns supply APY, borrow APY, utilization, TVL, and risk scores.
        """
        try:
            raw = await self._llama.get_pools()
        except Exception as e:
            logger.error(f"Failed to fetch lending pools: {e}")
            return []

        # Filter to lending pools only
        lending_keywords = {"lend", "lending", "supply", "borrow", "cdp", "earn"}
        results = []

        for pool in raw:
            category = (_pool_value(pool, "category", default="") or "").lower()
            project = (_pool_value(pool, "project", default="") or "").lower()
            pool_chain = (_pool_value(pool, "chain", default="") or "").lower()
            symbol = (_pool_value(pool, "symbol", default="") or "").lower()

            # Filter to lending pools
            is_lending = (
                "lending" in category
                or any(k in category for k in lending_keywords)
                or any(k in project for k in {"aave", "compound", "morpho", "spark",
                                               "solend", "marginfi", "kamino", "euler",
                                               "radiant", "benqi", "venus", "granary"})
            )
            if not is_lending:
                continue

            if chain and pool_chain != chain.lower():
                continue
            if protocol and protocol.lower() not in project:
                continue
            if asset and asset.upper() not in (_pool_value(pool, "symbol", default="") or "").upper():
                continue

            # Find matching protocol metadata
            proto_id = None
            for pid, pinfo in LENDING_PROTOCOLS.items():
                if pid in project or pinfo["display_name"].lower() in project:
                    proto_id = pid
                    break

            tvl = _pool_value(pool, "tvl_usd", "tvlUsd", 0) or 0
            apy_supply = _pool_value(pool, "apy_base", "apyBase") or _pool_value(pool, "apy", default=0) or 0
            apy_borrow = _pool_value(pool, "apy_borrow", "apyBorrow", 0) or 0
            utilization = _pool_value(pool, "utilization") or (
                apy_borrow / max(apy_supply, 0.01) * 0.8 if apy_supply > 0 else 0
            )

            market_risk = self._score_market_risk({
                **pool,
                "apyBorrow": apy_borrow,
                "utilization": utilization,
            })

            proto_risk = {}
            if proto_id:
                proto_risk = self._score_protocol_risk(proto_id, tvl)

            proto_info = LENDING_PROTOCOLS.get(proto_id, {}) if proto_id else {}

            results.append({
                "pool_id": _pool_value(pool, "pool_id", "pool"),
                "protocol": _pool_value(pool, "project"),
                "protocol_display": proto_info.get("display_name", _pool_value(pool, "project")),
                "symbol": _pool_value(pool, "symbol"),
                "chain": _pool_value(pool, "chain"),
                "tvlUsd": tvl,
                "apy_supply": round(apy_supply, 4),
                "apy_borrow": round(apy_borrow, 4),
                "utilization_pct": round(utilization * 100, 1),
                "audit_status": proto_info.get("audit_status", "unknown"),
                "auditors": proto_info.get("auditors", []),
                "incident_note": proto_info.get("incident_note"),
                "market_risk": market_risk,
                "protocol_risk": proto_risk,
                "combined_risk_score": (
                    market_risk["risk_score"] * 0.6
                    + (proto_risk.get("risk_score", 40)) * 0.4
                ),
            })

        # Sort by TVL descending
        results.sort(key=lambda x: x.get("tvlUsd") or 0, reverse=True)
        return results[:limit]

    async def compare_rates(
        self,
        asset: str,
        chains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Compare supply and borrow rates for an asset across all major
        lending protocols.

        Returns a sorted comparison table: best supply rate first,
        lowest borrow rate second, with risk scores for each.
        """
        markets = await self.get_lending_markets(asset=asset, limit=200)

        if chains:
            lower_chains = [c.lower() for c in chains]
            markets = [m for m in markets if (m.get("chain") or "").lower() in lower_chains]

        # Sort by best supply rate
        by_supply = sorted(markets, key=lambda m: m.get("apy_supply") or 0, reverse=True)
        # Sort by lowest borrow rate
        by_borrow = sorted(markets, key=lambda m: m.get("apy_borrow") or 0)

        return {
            "asset": asset.upper(),
            "markets_found": len(markets),
            "best_supply": by_supply[:5],
            "lowest_borrow": [m for m in by_borrow if (m.get("apy_borrow") or 0) > 0][:5],
            "all_markets": markets[:20],
        }

    async def get_protocol_overview(self, protocol_slug: str) -> Optional[Dict[str, Any]]:
        """
        Get a full lending protocol overview: TVL, markets, risk.
        """
        info = LENDING_PROTOCOLS.get(protocol_slug)
        if not info:
            # Try fuzzy match
            for pid, pinfo in LENDING_PROTOCOLS.items():
                if protocol_slug.lower() in pinfo["display_name"].lower():
                    protocol_slug = pid
                    info = pinfo
                    break

        if not info:
            return None

        # Fetch TVL from DefiLlama
        try:
            tvl_data = await self._llama.get_protocol_tvl(info["tvl_slug"])
        except Exception:
            tvl_data = {}

        current_tvl = (tvl_data or {}).get("tvl", 0)
        if isinstance(current_tvl, list):
            current_tvl = current_tvl[-1].get("totalLiquidityUSD", 0) if current_tvl else 0

        markets = await self.get_lending_markets(protocol=protocol_slug, limit=20)
        risk = self._score_protocol_risk(protocol_slug, current_tvl)

        return {
            "protocol": protocol_slug,
            "display_name": info["display_name"],
            "chains": info["chains"],
            "tvl_usd": current_tvl,
            "audit_status": info.get("audit_status", "unknown"),
            "auditors": info.get("auditors", []),
            "docs_url": info.get("docs_url"),
            "incident_note": info.get("incident_note"),
            "liquidation_threshold": LIQUIDATION_THRESHOLDS.get(protocol_slug),
            "risk": risk,
            "top_markets": markets[:10],
        }

    async def close(self):
        await self._llama.close()
