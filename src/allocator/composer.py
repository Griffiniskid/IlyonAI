"""Allocation composer: pools + risk budget → ranked positions with weights.

Consumes normalised DefiLlama pool dicts and produces typed AllocationPosition
records ready for `AllocationPayload`. Pure function — no network or state.

The scoring model here matches the Sentinel rubric exposed in
`src/agents/sentinel.py` but is dimensioned per-pool (Safety, Yield Durability,
Exit Liquidity, Confidence). We avoid importing the full SentinelAgent because
the agent is a live watcher over wallets; this is a stateless rollup.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from src.api.schemas.agent import AllocationPosition, ChainTone, RiskLevelLower, StrategyFit


_CHAIN_MAP: dict[str, ChainTone] = {
    "ethereum": "eth",
    "eth": "eth",
    "mainnet": "mainnet",
    "arbitrum": "arb",
    "arb": "arb",
    "solana": "sol",
    "sol": "sol",
    "base": "base",
    "polygon": "polygon",
    "bsc": "bsc",
    "binance": "bsc",
    "optimism": "op",
    "op": "op",
    "avalanche": "avax",
    "avax": "avax",
}

_ROUTER_BY_CHAIN: dict[ChainTone, str] = {
    "eth": "Enso",
    "mainnet": "Enso",
    "arb": "Enso",
    "base": "Enso",
    "polygon": "Enso",
    "bsc": "PancakeSwap",
    "op": "Enso",
    "avax": "Enso",
    "sol": "Jupiter",
}

_POSITION_CAP = 35  # demo-mandated max weight per position
_MIN_TVL_USD = 200_000_000.0  # $200M — demo-mandated
_MAX_POSITIONS = 5


@dataclass(frozen=True)
class PoolCandidate:
    """Normalised input for the composer."""
    project: str
    symbol: str
    chain: str
    tvl_usd: float
    apy: float
    audits: bool
    days_live: int
    stable: bool
    il_risk: str  # "no" | "yes"
    exposure: str  # "single" | "multi"
    raw_flags: tuple[str, ...] = ()


def normalise_chain(chain_raw: str) -> ChainTone:
    return _CHAIN_MAP.get(chain_raw.lower(), "mainnet")


def score_safety(pool: PoolCandidate) -> int:
    """Audit-present + high TVL + single exposure → higher safety."""
    s = 40
    if pool.audits:
        s += 25
    if pool.tvl_usd >= 1_000_000_000:
        s += 20
    elif pool.tvl_usd >= 500_000_000:
        s += 12
    elif pool.tvl_usd >= _MIN_TVL_USD:
        s += 6
    if pool.exposure == "single":
        s += 10
    if pool.il_risk == "no":
        s += 5
    return max(0, min(100, s))


def score_durability(pool: PoolCandidate) -> int:
    """Yield durability: not absurd APY + tenure + stability."""
    s = 30
    if pool.days_live >= 365:
        s += 25
    elif pool.days_live >= 180:
        s += 15
    if pool.apy <= 15:
        s += 25
    elif pool.apy <= 30:
        s += 12
    elif pool.apy <= 60:
        s += 4
    if pool.stable:
        s += 10
    return max(0, min(100, s))


def score_exit(pool: PoolCandidate) -> int:
    """Exit liquidity: higher TVL + stablecoin denom → easier exit."""
    s = 35
    if pool.tvl_usd >= 2_000_000_000:
        s += 35
    elif pool.tvl_usd >= 500_000_000:
        s += 25
    elif pool.tvl_usd >= _MIN_TVL_USD:
        s += 15
    if pool.stable:
        s += 12
    if pool.exposure == "single":
        s += 10
    return max(0, min(100, s))


def score_confidence(pool: PoolCandidate) -> int:
    """Confidence: audits + tenure."""
    s = 40
    if pool.audits:
        s += 20
    if pool.days_live >= 720:
        s += 25
    elif pool.days_live >= 365:
        s += 18
    elif pool.days_live >= 180:
        s += 8
    return max(0, min(100, s))


def weighted_sentinel(safety: int, durability: int, exit_: int, confidence: int) -> int:
    """Demo-matching blend: 0.40 safety, 0.25 durability, 0.20 exit, 0.15 confidence."""
    raw = 0.40 * safety + 0.25 * durability + 0.20 * exit_ + 0.15 * confidence
    return int(round(raw))


def bucket_risk(sentinel: int) -> RiskLevelLower:
    if sentinel >= 82:
        return "low"
    if sentinel >= 65:
        return "medium"
    return "high"


def bucket_fit(sentinel: int, apy: float) -> StrategyFit:
    if sentinel >= 88 and apy <= 8:
        return "conservative"
    if apy >= 12 or sentinel < 78:
        return "aggressive"
    return "balanced"


def derive_flags(pool: PoolCandidate, sentinel: int) -> list[str]:
    flags: list[str] = list(pool.raw_flags)
    if not pool.audits:
        flags.append("Unaudited")
    if pool.days_live < 180:
        flags.append("< 180 days live")
    if pool.il_risk == "yes":
        flags.append("IL risk")
    if pool.exposure == "multi":
        flags.append("Multi-asset exposure")
    if pool.apy > 25 and sentinel < 78:
        flags.append("Elevated APY vs. peers")
    return flags


def _format_tvl(usd: float) -> str:
    if usd >= 1_000_000_000:
        return f"${usd / 1_000_000_000:.1f}B"
    if usd >= 1_000_000:
        return f"${usd / 1_000_000:.0f}M"
    return f"${usd:,.0f}"


def _format_usd(usd: float) -> str:
    return f"${usd:,.0f}"


def _format_apy(apy: float) -> str:
    return f"{apy:.1f}%"


def _risk_floor(risk_budget: StrategyFit) -> int:
    """Minimum per-position Sentinel score required for this risk budget."""
    if risk_budget == "conservative":
        return 82
    if risk_budget == "balanced":
        return 70
    return 55


def _desired_mix(risk_budget: StrategyFit) -> dict[RiskLevelLower, int]:
    """Target count of low/medium/high risk slots for a 5-position ladder."""
    if risk_budget == "conservative":
        return {"low": 4, "medium": 1, "high": 0}
    if risk_budget == "balanced":
        return {"low": 3, "medium": 1, "high": 1}
    return {"low": 2, "medium": 2, "high": 1}


def rank_candidates(
    pools: Iterable[PoolCandidate],
    risk_budget: StrategyFit = "balanced",
) -> list[tuple[PoolCandidate, int, int, int, int]]:
    """Return pools sorted by weighted sentinel, filtered by risk floor.

    Each entry is (pool, safety, durability, exit, confidence).
    """
    floor = _risk_floor(risk_budget)
    scored: list[tuple[PoolCandidate, int, int, int, int, int]] = []
    for p in pools:
        if p.tvl_usd < _MIN_TVL_USD:
            continue
        if p.days_live < 180:
            continue
        if p.apy > 500:
            continue  # demo rejects junk APY
        s = score_safety(p)
        d = score_durability(p)
        e = score_exit(p)
        c = score_confidence(p)
        sent = weighted_sentinel(s, d, e, c)
        if sent < floor:
            continue
        scored.append((p, s, d, e, c, sent))
    scored.sort(key=lambda t: t[-1], reverse=True)
    return [(p, s, d, e, c) for (p, s, d, e, c, _) in scored]


def _assign_weights(positions: int, risk_budget: StrategyFit) -> list[int]:
    """Emit a weight ladder that sums to 100 and respects the position cap."""
    if positions == 0:
        return []
    if positions == 1:
        return [100]
    if risk_budget == "conservative":
        base = [35, 25, 20, 12, 8]
    elif risk_budget == "balanced":
        base = [35, 20, 20, 15, 10]
    else:
        base = [30, 25, 20, 15, 10]
    # Truncate + rescale
    trimmed = base[:positions]
    total = sum(trimmed)
    out = [int(round(w * 100 / total)) for w in trimmed]
    # Fix rounding drift
    drift = 100 - sum(out)
    if drift != 0:
        out[0] += drift
    # Respect cap
    return [min(_POSITION_CAP, w) for w in out]


def compose_allocation(
    pools: Sequence[PoolCandidate],
    usd_amount: float,
    risk_budget: StrategyFit = "balanced",
) -> list[AllocationPosition]:
    """Pick top-N pools + assign weights, returning typed positions.

    Applies the demo's risk ladder: one `medium` slot in balanced mode,
    none in conservative. Also enforces chain diversity — no more than 2
    positions on the same chain.
    """
    ranked = rank_candidates(pools, risk_budget=risk_budget)
    if not ranked:
        return []
    mix_target = _desired_mix(risk_budget)
    selected: list[tuple[PoolCandidate, int, int, int, int, RiskLevelLower]] = []
    per_chain: dict[str, int] = {}

    def _slot(risk: RiskLevelLower) -> bool:
        taken = sum(1 for (_, _, _, _, _, r) in selected if r == risk)
        return taken < mix_target.get(risk, 0)

    for (p, s, d, e, c) in ranked:
        if len(selected) >= _MAX_POSITIONS:
            break
        sent = weighted_sentinel(s, d, e, c)
        risk = bucket_risk(sent)
        if not _slot(risk):
            continue
        chain_count = per_chain.get(p.chain.lower(), 0)
        if chain_count >= 3:
            continue
        selected.append((p, s, d, e, c, risk))
        per_chain[p.chain.lower()] = chain_count + 1

    # Fallback — if risk mix couldn't be filled (thin universe), relax.
    if len(selected) < _MAX_POSITIONS:
        for (p, s, d, e, c) in ranked:
            if len(selected) >= _MAX_POSITIONS:
                break
            if any(sp is p for (sp, _, _, _, _, _) in selected):
                continue
            chain_count = per_chain.get(p.chain.lower(), 0)
            if chain_count >= 2:
                continue
            sent = weighted_sentinel(s, d, e, c)
            risk = bucket_risk(sent)
            selected.append((p, s, d, e, c, risk))
            per_chain[p.chain.lower()] = chain_count + 1

    weights = _assign_weights(len(selected), risk_budget)
    positions: list[AllocationPosition] = []
    for rank_idx, ((p, s, d, e, c, risk), weight) in enumerate(zip(selected, weights), start=1):
        sent = weighted_sentinel(s, d, e, c)
        chain = normalise_chain(p.chain)
        fit = bucket_fit(sent, p.apy)
        flags = derive_flags(p, sent)
        positions.append(
            AllocationPosition(
                rank=rank_idx,
                protocol=p.project,
                asset=p.symbol,
                chain=chain,
                apy=_format_apy(p.apy),
                sentinel=sent,
                risk=risk,
                fit=fit,
                weight=weight,
                usd=_format_usd(usd_amount * weight / 100.0),
                tvl=_format_tvl(p.tvl_usd),
                router=_ROUTER_BY_CHAIN.get(chain, "Enso"),
                safety=s,
                durability=d,
                exit=e,
                confidence=c,
                flags=flags,
            )
        )
    return positions


def summarise_positions(
    positions: Sequence[AllocationPosition], usd_amount: float
) -> dict:
    """Derive top-level aggregate fields used by AllocationPayload."""
    if not positions:
        return {
            "total_usd": _format_usd(usd_amount),
            "blended_apy": "0.0%",
            "chains": 0,
            "weighted_sentinel": 0,
            "risk_mix": {"low": 0, "medium": 0, "high": 0},
            "combined_tvl": "$0",
        }
    chains = {p.chain for p in positions}
    risk_mix = {"low": 0, "medium": 0, "high": 0}
    for p in positions:
        risk_mix[p.risk] += 1
    # Blended APY: weight-sum of numeric APYs
    apy_num = sum(float(p.apy.rstrip("%")) * p.weight for p in positions) / 100.0
    # Weighted Sentinel
    ws = int(round(sum(p.sentinel * p.weight for p in positions) / 100.0))
    # Combined TVL parse
    combined_usd = 0.0
    for p in positions:
        raw = p.tvl.lstrip("$")
        mult = 1.0
        if raw.endswith("B"):
            mult = 1_000_000_000
            raw = raw[:-1]
        elif raw.endswith("M"):
            mult = 1_000_000
            raw = raw[:-1]
        try:
            combined_usd += float(raw) * mult
        except ValueError:
            pass
    return {
        "total_usd": _format_usd(usd_amount),
        "blended_apy": f"~{apy_num:.1f}%",
        "chains": len(chains),
        "weighted_sentinel": ws,
        "risk_mix": risk_mix,
        "combined_tvl": _format_tvl(combined_usd),
    }


def execution_steps_from_positions(
    positions: Sequence[AllocationPosition], usd_amount: float
) -> list[dict]:
    """Turn positions into execution steps (for ExecutionPlanPayload)."""
    from src.api.schemas.agent import ExecutionStep

    steps: list[ExecutionStep] = []
    # Chain → wallet mapping
    wallet_by_chain = {
        "sol": "Phantom",
        "eth": "MetaMask",
        "mainnet": "MetaMask",
        "arb": "MetaMask",
        "base": "MetaMask",
        "polygon": "MetaMask",
        "bsc": "MetaMask",
        "op": "MetaMask",
        "avax": "MetaMask",
    }
    # Gas baseline per chain (USD)
    gas_by_chain = {
        "eth": 4.8, "mainnet": 6.9, "arb": 0.35, "base": 0.25, "polygon": 0.08,
        "bsc": 0.12, "op": 0.35, "avax": 0.3, "sol": 0.01,
    }
    # Verb by pool category — naive but demo-faithful
    def _verb(asset: str, chain: ChainTone) -> str:
        a = asset.upper()
        if "USD" in a or "DAI" in a or "USDC" in a:
            return "Supply"
        if chain == "sol" and "SOL" in a:
            return "Liquid stake"
        if "ETH" in a or "STETH" in a or "RETH" in a:
            return "Stake"
        if a.startswith("PT-") or "PT-" in a:
            return "Deposit"
        return "Allocate"

    # Native asset amount — if stable pool, dollars == asset units; else demo ratio (for ETH at $3100, etc.)
    approx_native_price = {
        "eth": 3100.0, "mainnet": 3100.0, "arb": 3100.0, "base": 3100.0, "op": 3100.0,
        "polygon": 0.70, "bsc": 620.0, "avax": 28.0,
        "sol": 85.0,
    }
    for p in positions:
        usd_slice = usd_amount * p.weight / 100.0
        a = p.asset.upper()
        is_stable = any(s in a for s in ("USD", "DAI", "FRAX", "USDC", "USDT"))
        if is_stable:
            amount_num = usd_slice
            amount_asset = "USDC"
        elif "ETH" in a:
            amount_num = usd_slice / approx_native_price.get(p.chain, 3100.0)
            amount_asset = "ETH"
        elif "SOL" in a:
            amount_num = usd_slice / approx_native_price.get(p.chain, 85.0)
            amount_asset = "SOL"
        else:
            amount_num = usd_slice
            amount_asset = "USDC"
        amount_str = (
            f"{amount_num:,.3f}" if amount_num < 100 else f"{amount_num:,.0f}"
        )
        gas_usd = gas_by_chain.get(p.chain, 2.0)
        steps.append(
            ExecutionStep(
                index=p.rank,
                verb=_verb(p.asset, p.chain),
                amount=amount_str,
                asset=amount_asset,
                target=f"{p.asset} · {p.protocol}",
                chain=p.chain,
                router=p.router,
                wallet=wallet_by_chain.get(p.chain, "MetaMask"),
                gas=f"~${gas_usd:,.2f}",
                step_id=f"alloc_step_{p.rank}",
                protocol=p.protocol,
            )
        )
    return [s.model_dump() for s in steps]


def total_gas_from_steps(steps: Sequence[dict]) -> str:
    total = 0.0
    for s in steps:
        raw = s.get("gas", "~$0").lstrip("~$").replace(",", "")
        try:
            total += float(raw)
        except ValueError:
            pass
    return f"~${total:,.2f}"


def wallets_summary_from_steps(steps: Sequence[dict]) -> str:
    kinds = sorted({s.get("wallet", "MetaMask") for s in steps})
    return " + ".join(kinds) if kinds else "MetaMask"
