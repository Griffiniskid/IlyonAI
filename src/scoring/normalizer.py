from __future__ import annotations

from typing import Any

from src.allocator.composer import PoolCandidate


AUDIT_PROJECTS = {
    "lido",
    "rocket-pool",
    "rocketpool",
    "jito",
    "aave-v3",
    "aave-v2",
    "compound-v3",
    "compound-v2",
    "pendle",
    "curve-dex",
    "curve",
    "ether.fi",
    "ether-fi",
    "renzo",
    "etherfi",
    "spark",
    "morpho-blue",
    "makerdao",
    "convex-finance",
    "yearn-finance",
    "stargate",
    "hyperliquid",
}


def infer_audits(project_slug: str) -> bool:
    return project_slug.lower() in AUDIT_PROJECTS


def infer_stable(symbol: str, pool: dict[str, Any]) -> bool:
    if bool(pool.get("stablecoin")):
        return True
    stable_tokens = (
        "USDC",
        "USDT",
        "DAI",
        "FRAX",
        "LUSD",
        "USDE",
        "SUSDE",
        "USDY",
        "PYUSD",
        "GHO",
    )
    symbol_upper = symbol.upper()
    return any(token in symbol_upper for token in stable_tokens)


def infer_exposure(symbol: str) -> str:
    return "multi" if "-" in symbol and not symbol.upper().startswith("PT-") else "single"


def infer_days_live(pool: dict[str, Any], audited: bool) -> int:
    explicit = pool.get("days_live") or pool.get("daysLive")
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass
    tvl = float(pool.get("tvlUsd") or pool.get("tvl_usd") or pool.get("liquidity_usd") or 0)
    if audited:
        return 720 if tvl >= 1_000_000_000 else 400
    return 200 if tvl >= 100_000_000 else 60


def pool_candidate_from_mapping(pool: dict[str, Any]) -> PoolCandidate:
    project = str(pool.get("project") or pool.get("protocol") or pool.get("protocol_name") or "Unknown")
    symbol = str(pool.get("symbol") or pool.get("asset") or pool.get("pair") or "?")
    audited = bool(pool.get("audits")) if "audits" in pool else infer_audits(project)
    tvl = float(pool.get("tvlUsd") or pool.get("tvl_usd") or pool.get("liquidity_usd") or 0)
    return PoolCandidate(
        project=project,
        symbol=symbol,
        chain=str(pool.get("chain") or pool.get("chain_name") or "Ethereum"),
        tvl_usd=tvl,
        apy=float(pool.get("apy") or pool.get("apr") or pool.get("yield") or 0),
        audits=audited,
        days_live=infer_days_live(pool, audited),
        stable=infer_stable(symbol, pool),
        il_risk=str(pool.get("ilRisk") or pool.get("il_risk") or "no"),
        exposure=str(pool.get("exposure") or infer_exposure(symbol)),
        raw_flags=tuple(str(flag) for flag in pool.get("flags", []) if str(flag).strip()),
    )
