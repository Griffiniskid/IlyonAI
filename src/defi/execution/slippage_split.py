"""Spec per-leg slippage split.

Single global 50bp default decomposes into per-leg budgets:
- swap_src: 15 bps
- bridge: 15 bps
- swap_dst: 20 bps
- stable-only path: 10 bps total (any leg)

Caller chooses the budget per leg kind. Floor: each leg >= 10 bps so the
aggregator gets a non-zero tolerance window.
"""
from __future__ import annotations

from typing import Literal

LegKind = Literal["swap_src", "bridge", "swap_dst", "stable_pair", "single_leg"]

DEFAULT_SPLIT_BPS: dict[str, int] = {
    "swap_src": 15,
    "bridge": 15,
    "swap_dst": 20,
    "stable_pair": 10,
    "single_leg": 50,
}

SLIPPAGE_FLOOR_BPS: int = 10


def slippage_for_leg(kind: LegKind, *, override: int | None = None) -> int:
    """Return per-leg slippage bps. User override wins (clamped to floor)."""
    if override is not None:
        return max(SLIPPAGE_FLOOR_BPS, int(override))
    return DEFAULT_SPLIT_BPS.get(kind, 50)


def split_total_budget(total_bps: int, leg_kinds: list[LegKind]) -> list[int]:
    """Distribute total_bps proportionally to default-weighted shares.

    Used when user gives a global override but plan has multiple legs.
    Each emitted leg respects the SLIPPAGE_FLOOR_BPS floor so the aggregator
    never receives a 0-bps tolerance window.
    """
    if not leg_kinds:
        return []
    weights = [DEFAULT_SPLIT_BPS.get(k, 50) for k in leg_kinds]
    total_weight = sum(weights)
    if total_weight == 0:
        return [SLIPPAGE_FLOOR_BPS] * len(leg_kinds)
    return [
        max(SLIPPAGE_FLOOR_BPS, int(total_bps * w / total_weight))
        for w in weights
    ]
