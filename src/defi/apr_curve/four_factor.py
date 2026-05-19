"""Four-factor APR composition per spec §6e.

Composes empirical P_in (already shipped in empirical_cdf.py) with closed-form:
- CE (capital efficiency): tight ranges concentrate liquidity, ~1/(width_pct)^0.5
- fee_yield_full: pool fee_apr_30d (annualized fee/TVL)
- IL_drag: Black-Scholes-like loss from price drift at given width × vol

Spec §6e mandates:
    APR(range_width) = P_in(width) * CE(width) * fee_yield_full(pool) - IL_drag(width, vol)

The empirical CDF in empirical_cdf.py already supplies P_in. This module assembles
the remaining three closed-forms and composes them point-wise across the bucket grid.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def capital_efficiency(width_bps: int) -> float:
    """CE multiplier vs full-range. Tight range -> high CE.

    Approximation: CE ~ 2 / (sqrt(1+r) - 1/sqrt(1+r)) where r=width_bps/10000.
    For width=10000bps (full), CE~1. For width=500bps (+/-5%), CE~20.
    """
    if width_bps <= 0:
        return 1.0
    r = width_bps / 10000.0
    if r >= 1.0:
        return 1.0
    sqrt_up = math.sqrt(1.0 + r)
    return 2.0 / (sqrt_up - 1.0 / sqrt_up)


def fee_yield_full(pool_fee_apr_30d: float | None) -> float:
    """Annualized fee yield at full range. From pool's 30d fee_apr."""
    return max(0.0, pool_fee_apr_30d or 0.0)


def il_drag(width_bps: int, vol_30d: float) -> float:
    """IL drag annualized at given width x 30d vol.

    Approximation (Loesch 2024 LP IL closed-form):
        IL_drag ~ vol_30d^2 * width_pct^2 / 8
    """
    if width_bps <= 0 or vol_30d <= 0:
        return 0.0
    width_pct = width_bps / 10000.0
    return (vol_30d ** 2) * (width_pct ** 2) / 8.0


def compose_apr_curve(
    p_in_curve: list[float],
    width_bps_curve: list[int],
    pool_fee_apr_30d: float | None,
    vol_30d: float,
) -> list[float]:
    """Point-wise compose APR over the empirical CDF buckets.

    Returns same-length list as p_in_curve with composed APR. Each bucket
    yields max(0, P_in * CE * fee_yield_full - IL_drag) so the curve never
    dips negative even when IL dominates fee accrual at extreme width/vol.
    Empty inputs -> empty output. Mismatched lengths zip to the shorter.
    """
    fy = fee_yield_full(pool_fee_apr_30d)
    out: list[float] = []
    for p_in, width_bps in zip(p_in_curve, width_bps_curve):
        ce = capital_efficiency(width_bps)
        il = il_drag(width_bps, vol_30d)
        composed = max(0.0, p_in * ce * fy - il)
        out.append(composed)
    return out


@dataclass(frozen=True)
class FourFactorAPRPoint:
    width_bps: int
    p_in: float
    ce: float
    fee_yield: float
    il_drag: float
    composed_apr: float
