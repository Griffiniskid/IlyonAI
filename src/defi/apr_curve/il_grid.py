"""Spec 5-scenario IL grid.

For a range LP preview, the planner emits a 5-scenario grid showing IL at
each scenario. Scenarios:
- -50% (price halves)
- -20% (moderate drop)
-   0% (no move)
- +20% (moderate rise)
- +50% (price doubles)

IL formula for full range: IL_full = 2·sqrt(r)/(1+r) - 1
For concentrated range [p_lo, p_hi]: scale by capital efficiency factor and
clip at range boundaries (LP becomes single-asset outside).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


IL_GRID_SCENARIOS: list[tuple[float, str]] = [
    (-0.50, "-50%"),
    (-0.20, "-20%"),
    (0.0, "0%"),
    (0.20, "+20%"),
    (0.50, "+50%"),
]


@dataclass(frozen=True)
class ILScenario:
    label: str
    price_ratio: float  # r = p_new / p_init
    il_pct: float       # IL as a decimal (-0.0568 = -5.68% IL)
    in_range: bool


def il_full_range(price_move_pct: float) -> float:
    """Closed-form IL for full-range V2-like LP. price_move_pct e.g. -0.5 = halve."""
    r = 1.0 + price_move_pct
    if r <= 0:
        return -1.0  # total loss approximation
    return (2.0 * math.sqrt(r) / (1.0 + r)) - 1.0


def il_concentrated(price_move_pct: float, width_bps: int) -> tuple[float, bool]:
    """IL for concentrated range. Returns (il_pct, in_range).

    `width_bps` is the half-width of the range in basis points (1bp = 0.01%).
    width_bps <= 0 means "full range" (no concentration).
    """
    if width_bps <= 0:
        return (il_full_range(price_move_pct), True)
    width_pct = width_bps / 10000.0
    if abs(price_move_pct) > width_pct:
        # Out of range → LP becomes single-asset, IL equals the price move
        # vs holding 50/50.
        return (-abs(price_move_pct) / 2.0, False)
    # In range: V3 IL scales by ~1/(width_pct) factor approximation
    full_il = il_full_range(price_move_pct)
    ce = max(1.0, 1.0 / width_pct)  # capital-efficiency factor
    return (full_il * ce, True)


def build_il_grid(width_bps: int) -> list[ILScenario]:
    """Build the 5-scenario IL grid for a given range width."""
    grid: list[ILScenario] = []
    for ratio, label in IL_GRID_SCENARIOS:
        il, in_range = il_concentrated(ratio, width_bps)
        grid.append(ILScenario(
            label=label,
            price_ratio=1.0 + ratio,
            il_pct=il,
            in_range=in_range,
        ))
    return grid
