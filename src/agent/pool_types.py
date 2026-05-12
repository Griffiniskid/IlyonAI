"""Explicit pool-type registry (Phase 1).

Replaces the substring-heuristic in `protocol_urls.classify_pool_kind`
with an explicit slug-to-PoolType map for every protocol we touch, plus
a substring fallback for slugs we haven't seen yet.
"""
from __future__ import annotations

from enum import Enum


class PoolType(str, Enum):
    V2_AMM = "v2_amm"
    V3_CLMM = "v3_clmm"
    DLMM = "dlmm"
    STABLE = "stable"
    VAULT = "vault"
    AUTO_VAULT_CLMM = "auto_vault_clmm"
    LST = "lst"
    LENDING = "lending"


POOL_TYPE_REGISTRY: dict[str, PoolType] = {
    # ── Solana ────────────────────────────────────────────────────────────
    "raydium-amm": PoolType.V2_AMM,
    "raydium-cp": PoolType.V2_AMM,
    "raydium-clmm": PoolType.V3_CLMM,
    "raydium-amm-v3": PoolType.V3_CLMM,
    "orca": PoolType.V2_AMM,
    "orca-dex": PoolType.V2_AMM,
    "orca-whirlpools": PoolType.V3_CLMM,
    "orca-clmm": PoolType.V3_CLMM,
    "meteora": PoolType.V2_AMM,
    "meteora-amm": PoolType.V2_AMM,
    "meteora-dlmm": PoolType.DLMM,
    "meteora-vault": PoolType.VAULT,
    "kamino-liquidity": PoolType.AUTO_VAULT_CLMM,
    "kamino-lend": PoolType.LENDING,
    "kamino-vault": PoolType.AUTO_VAULT_CLMM,
    "saber": PoolType.STABLE,
    "mercurial": PoolType.STABLE,
    "marinade-finance": PoolType.LST,
    "marinade-native": PoolType.LST,
    "marinade": PoolType.LST,
    "marinade-liquid-staking": PoolType.LST,
    "jito": PoolType.LST,
    "jito-liquid-staking": PoolType.LST,
    "sanctum": PoolType.LST,
    "sanctum-infinity": PoolType.LST,
    "sanctum-liquid-staking": PoolType.LST,
    "lifinity": PoolType.V2_AMM,
    "lifinity-v2": PoolType.V2_AMM,
    "drift": PoolType.LENDING,
    "lulo": PoolType.LENDING,
    "save": PoolType.LENDING,
    "solend": PoolType.LENDING,
    # ── EVM ───────────────────────────────────────────────────────────────
    "uniswap-v2": PoolType.V2_AMM,
    "uniswap-v3": PoolType.V3_CLMM,
    "uniswap-v4": PoolType.V3_CLMM,
    "uniswap": PoolType.V2_AMM,
    "sushiswap": PoolType.V2_AMM,
    "sushiswap-v3": PoolType.V3_CLMM,
    "pancakeswap": PoolType.V2_AMM,
    "pancakeswap-v2": PoolType.V2_AMM,
    "pancakeswap-amm": PoolType.V2_AMM,
    "pancakeswap-v3": PoolType.V3_CLMM,
    "pancakeswap-amm-v3": PoolType.V3_CLMM,
    "pancakeswap-stableswap": PoolType.STABLE,
    "aerodrome": PoolType.V2_AMM,
    "aerodrome-v1": PoolType.V2_AMM,
    "aerodrome-slipstream": PoolType.V3_CLMM,
    "aerodrome-cl": PoolType.V3_CLMM,
    "velodrome": PoolType.V2_AMM,
    "velodrome-v1": PoolType.V2_AMM,
    "velodrome-v2": PoolType.V2_AMM,
    # LLM sometimes hallucinates "velodrome-v3" — real Velodrome has Slipstream
    # for concentrated liquidity, no actual V3. Coerce to V2 so the pool_link
    # card emits the Velodrome app URL instead of the V3 redirect.
    "velodrome-v3": PoolType.V2_AMM,
    "velodrome-finance": PoolType.V2_AMM,
    "velodrome-slipstream": PoolType.V3_CLMM,
    "camelot": PoolType.V2_AMM,
    "camelot-v3": PoolType.V3_CLMM,
    "quickswap": PoolType.V2_AMM,
    "quickswap-v3": PoolType.V3_CLMM,
    "trader-joe-v1": PoolType.V2_AMM,
    "trader-joe-v2": PoolType.V3_CLMM,
    "baseswap": PoolType.V2_AMM,
    "ramses-v2": PoolType.V3_CLMM,
    "ramses-cl": PoolType.V3_CLMM,
    "thena": PoolType.V2_AMM,
    "thena-v3": PoolType.V3_CLMM,
    "thena-fusion": PoolType.V3_CLMM,
    "curve-dex": PoolType.STABLE,
    "curve": PoolType.STABLE,
    "balancer": PoolType.STABLE,
    "balancer-v2": PoolType.STABLE,
    "balancer-v3": PoolType.STABLE,
    "aave-v3": PoolType.LENDING,
    "aave-v2": PoolType.LENDING,
    "aave": PoolType.LENDING,
    "compound-v3": PoolType.LENDING,
    "compound": PoolType.LENDING,
    "morpho-blue": PoolType.LENDING,
    "morpho": PoolType.LENDING,
    "spark": PoolType.LENDING,
    "yearn-finance": PoolType.VAULT,
    "yearn": PoolType.VAULT,
    "beefy": PoolType.VAULT,
    "convex-finance": PoolType.VAULT,
    "moonwell": PoolType.LENDING,
    "pendle": PoolType.VAULT,
    "venus": PoolType.LENDING,
    "benqi-liquid-staking": PoolType.LST,
    "gamma": PoolType.AUTO_VAULT_CLMM,
    "arrakis": PoolType.AUTO_VAULT_CLMM,
    "steer-protocol": PoolType.AUTO_VAULT_CLMM,
    "lido": PoolType.LST,
    "rocket-pool": PoolType.LST,
    "ether.fi-stake": PoolType.LST,
    "ether-fi": PoolType.LST,
    "frax-ether": PoolType.LST,
    "swell-network": PoolType.LST,
    "stader": PoolType.LST,
    "lista-dao": PoolType.LST,
    "blackhole-clmm": PoolType.V3_CLMM,
    "supernova-cl": PoolType.V3_CLMM,
    "shadow-exchange-clmm": PoolType.V3_CLMM,
    "kim": PoolType.V3_CLMM,
}


def lookup_pool_type(protocol_slug: str | None) -> PoolType:
    """Explicit registry first; substring heuristic only for unknown slugs."""
    if not protocol_slug:
        return PoolType.V2_AMM
    norm = protocol_slug.lower().strip()
    if norm in POOL_TYPE_REGISTRY:
        return POOL_TYPE_REGISTRY[norm]
    if any(h in norm for h in ("v3", "v4", "clmm", "slipstream", "concentrated", "kim", "fusion", "whirlpool")):
        return PoolType.V3_CLMM
    if "dlmm" in norm:
        return PoolType.DLMM
    if any(h in norm for h in ("curve", "balancer", "saddle", "mim-swap", "saber", "mercurial")):
        return PoolType.STABLE
    if any(h in norm for h in ("aave", "compound", "morpho", "spark", "moonwell", "venus", "drift", "lulo", "save", "solend")):
        return PoolType.LENDING
    if any(h in norm for h in ("yearn", "beefy", "convex", "pendle", "gamma", "arrakis", "steer", "ichi")):
        return PoolType.VAULT
    if any(h in norm for h in ("lido", "rocket", "ether.fi", "ether-fi", "etherfi", "frax-ether", "swell", "stader", "marinade", "jito", "sanctum")):
        return PoolType.LST
    return PoolType.V2_AMM


def kind_for_card(protocol_slug: str | None) -> str:
    """Map PoolType to the string the pool_link / pool_deposit_v3 cards
    use today: 'v2' | 'v3' | 'stable' | 'vault'."""
    pt = lookup_pool_type(protocol_slug)
    if pt in (PoolType.V3_CLMM, PoolType.DLMM):
        return "v3"
    if pt == PoolType.STABLE:
        return "stable"
    if pt in (PoolType.VAULT, PoolType.AUTO_VAULT_CLMM, PoolType.LST):
        return "vault"
    if pt == PoolType.LENDING:
        return "vault"
    return "v2"
