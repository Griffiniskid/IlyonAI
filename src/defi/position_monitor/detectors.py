"""Position-health alert detectors (V7-024).

Spec §4: each detector reads recent PositionHealth snapshots (or simple pool
metrics) and emits a `PositionAlert`-shaped dict when its threshold is
breached. All four detectors are pure functions — no I/O, no DB, no clock
reads beyond what callers feed in — so they're trivially unit-testable with
synthetic data.

Alert dict shape (uniform across detectors):

    {
        "alert_type": "OUT_OF_RANGE" | "FEE_APR_DROP" | "TVL_EXODUS" | "GAS_FAVORABLE",
        "severity":   "info" | "warning" | "critical",
        "message":    str,        # human-readable summary
        "payload":    dict,       # detector-specific structured data
    }

Detectors return `None` when the threshold is not breached.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# EVM chains where a gas-oracle / gwei comparison is meaningful. Anything
# outside this set (e.g. Solana, Sui, Aptos) returns None from the gas
# detector because the chain has no gwei semantics.
_EVM_CHAINS: frozenset[str] = frozenset({
    "ethereum",
    "arbitrum",
    "optimism",
    "polygon",
    "base",
    "bnb",
    "bsc",
    "avalanche",
    "fantom",
    "gnosis",
    "linea",
    "scroll",
    "zksync",
    "mantle",
    "celo",
    "blast",
    "mode",
    "metis",
})


def _parse_snapshot_at(value) -> Optional[datetime]:
    """Best-effort timestamp parse — accepts datetime, ISO string, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def detect_out_of_range(
    snapshots: list[dict],
    threshold_hours: int = 24,
) -> Optional[dict]:
    """Fire if a V3-style position has been out-of-range for ≥ threshold_hours.

    Looks at the most recent CONTIGUOUS tail of snapshots where `in_range`
    is False. If that tail spans at least `threshold_hours`, returns an
    alert. Otherwise returns None.

    Span is measured from snapshot timestamps when present; otherwise we
    assume one snapshot per hour (so 24 contiguous False snapshots ≈ 24h).
    This dual-mode lets us drive the detector both from real cron data
    (5-min cadence with `snapshot_at`) and from terse synthetic fixtures.

    Snapshots without an `in_range` key are V2 / stable-style and the
    concept doesn't apply — we return None without inspecting them.
    """
    if not snapshots:
        return None

    # V2 / stable positions: no concentrated-liquidity range concept.
    if "in_range" not in snapshots[0]:
        return None

    # Walk the tail backwards, collecting the contiguous suffix of False.
    tail: list[dict] = []
    for snap in reversed(snapshots):
        if snap.get("in_range") is False:
            tail.append(snap)
        else:
            break

    if not tail:
        return None

    # Measure the span. Prefer real timestamps if both ends have them.
    tail_ordered = list(reversed(tail))  # oldest → newest
    first_ts = _parse_snapshot_at(tail_ordered[0].get("snapshot_at"))
    last_ts = _parse_snapshot_at(tail_ordered[-1].get("snapshot_at"))

    if first_ts is not None and last_ts is not None:
        span_hours = (last_ts - first_ts).total_seconds() / 3600.0
    else:
        # Fallback: assume one snapshot per hour.
        span_hours = float(len(tail))

    if span_hours < threshold_hours:
        return None

    position_id = tail_ordered[-1].get("position_id", "<unknown>")
    return {
        "alert_type": "OUT_OF_RANGE",
        "severity": "warning",
        "message": (
            f"Position {position_id} has been out of range for "
            f"{span_hours:.1f}h (threshold {threshold_hours}h). "
            f"Fees stopped accruing — consider rebalancing or migrating."
        ),
        "payload": {
            "position_id": position_id,
            "hours_out_of_range": round(span_hours, 2),
            "threshold_hours": threshold_hours,
            "contiguous_snapshots": len(tail),
        },
    }


def detect_fee_apr_drop(
    snapshots: list[dict],
    drop_threshold_pct: float = 0.5,
) -> Optional[dict]:
    """Fire if realized fee APR dropped ≥ drop_threshold_pct vs prior 24h avg.

    Compares the most recent snapshot's `realized_fee_apr` against the
    arithmetic mean of the preceding window (up to the previous 24
    snapshots, or all preceding snapshots if fewer). Drop is computed as
    `(prior_avg - current) / prior_avg`. A positive drop_threshold_pct
    means we only fire on real drops; we never fire when fees increase.

    Requires at least 2 snapshots (1 current + ≥1 baseline). Returns None
    if the baseline average is non-positive (can't compute a drop ratio).
    """
    if not snapshots or len(snapshots) < 2:
        return None

    current_snap = snapshots[-1]
    current_apr = current_snap.get("realized_fee_apr")
    if current_apr is None:
        return None
    current_apr = float(current_apr)

    # Baseline: up to 24 prior snapshots (interpreted as ~24h window).
    prior_window = snapshots[-25:-1] if len(snapshots) > 25 else snapshots[:-1]
    prior_aprs = [
        float(s["realized_fee_apr"])
        for s in prior_window
        if s.get("realized_fee_apr") is not None
    ]
    if not prior_aprs:
        return None

    prior_avg = sum(prior_aprs) / len(prior_aprs)
    if prior_avg <= 0:
        # Avoid div-by-zero / can't meaningfully compute a "drop" off zero.
        return None

    drop_ratio = (prior_avg - current_apr) / prior_avg
    if drop_ratio < drop_threshold_pct:
        return None

    position_id = current_snap.get("position_id", "<unknown>")
    return {
        "alert_type": "FEE_APR_DROP",
        "severity": "warning",
        "message": (
            f"Position {position_id} fee APR dropped "
            f"{drop_ratio * 100:.1f}% (from {prior_avg:.2f}% avg to "
            f"{current_apr:.2f}%). Pool activity may be cooling — "
            f"consider exit or migration."
        ),
        "payload": {
            "position_id": position_id,
            "current_apr": current_apr,
            "prior_avg_apr": round(prior_avg, 4),
            "drop_pct": round(drop_ratio, 4),
            "drop_threshold_pct": drop_threshold_pct,
            "baseline_snapshots": len(prior_aprs),
        },
    }


def detect_tvl_exodus(
    pool_tvl_history: list[float],
    window_hours: int = 24,
    threshold_pct: float = 0.3,
) -> Optional[dict]:
    """Fire if pool TVL fell ≥ threshold_pct over the trailing window.

    `pool_tvl_history` is an ordered (oldest → newest) list of TVL USD
    values. We compare the head of the trailing `window_hours` slice
    against the tail (current). If the drop ratio meets/exceeds
    `threshold_pct`, we fire.

    Assumes one TVL sample per hour (matches the common Defillama /
    internal pool-history cadence). If fewer than `window_hours` samples
    are provided, we use whatever is available (≥2 samples required).
    """
    if not pool_tvl_history or len(pool_tvl_history) < 2:
        return None

    window = pool_tvl_history[-window_hours:] if len(pool_tvl_history) > window_hours else pool_tvl_history
    start_tvl = float(window[0])
    current_tvl = float(window[-1])
    if start_tvl <= 0:
        return None

    drop_ratio = (start_tvl - current_tvl) / start_tvl
    if drop_ratio < threshold_pct:
        return None

    return {
        "alert_type": "TVL_EXODUS",
        "severity": "critical" if drop_ratio >= 0.5 else "warning",
        "message": (
            f"Pool TVL dropped {drop_ratio * 100:.1f}% in the last "
            f"{len(window)}h (from ${start_tvl:,.0f} to ${current_tvl:,.0f}). "
            f"Large exits may signal protocol issues or yield collapse."
        ),
        "payload": {
            "start_tvl_usd": start_tvl,
            "current_tvl_usd": current_tvl,
            "drop_pct": round(drop_ratio, 4),
            "threshold_pct": threshold_pct,
            "window_hours": len(window),
        },
    }


def detect_gas_favorable(
    chain: str,
    current_gas_gwei: float,
    threshold_gwei: float = 30.0,
) -> Optional[dict]:
    """Fire on EVM chains when gas is cheap enough to recommend rebalancing.

    Returns None for any non-EVM chain (e.g. Solana) since gwei has no
    meaning there. Returns None on EVM if gas is above the threshold.
    Otherwise returns an info-severity alert nudging the user to act
    while fees are low.
    """
    if not chain:
        return None
    chain_slug = chain.strip().lower()
    if chain_slug not in _EVM_CHAINS:
        return None

    if current_gas_gwei is None or current_gas_gwei > threshold_gwei:
        return None

    return {
        "alert_type": "GAS_FAVORABLE",
        "severity": "info",
        "message": (
            f"Gas on {chain_slug} is {current_gas_gwei:.1f} gwei "
            f"(≤ {threshold_gwei:.1f} gwei threshold). Good window to "
            f"rebalance, claim, or migrate while fees are cheap."
        ),
        "payload": {
            "chain": chain_slug,
            "current_gas_gwei": float(current_gas_gwei),
            "threshold_gwei": float(threshold_gwei),
        },
    }


__all__ = [
    "detect_out_of_range",
    "detect_fee_apr_drop",
    "detect_tvl_exodus",
    "detect_gas_favorable",
]
