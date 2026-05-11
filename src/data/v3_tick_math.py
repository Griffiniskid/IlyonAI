"""Uniswap V3 tick math.

Pure-Python implementation of the parts we need:
  * sqrt_price_x96_from_tick / tick_from_sqrt_price_x96
  * price_from_tick (token1 per token0)
  * align_tick (snap to tick_spacing)
  * optimal_ratio_for_range (token0:token1 USD split for single-sided zap)

Uses Decimal where we can lose precision through float — the production V3 SDK
uses BigInt sqrt math; for range/APR display + optimal ratio we don't need
full BigInt precision because we're already approximating user intent.
"""
from __future__ import annotations

import math
from decimal import Decimal, getcontext

getcontext().prec = 60

Q96 = Decimal(2) ** 96
_LN_BASE = Decimal("1.0001").ln()


def sqrt_price_x96_from_tick(tick: int) -> int:
    """Return sqrtPriceX96 = sqrt(1.0001^tick) * 2^96 as an integer."""
    sqrt_price = (Decimal("1.0001") ** Decimal(tick)).sqrt()
    return int(sqrt_price * Q96)


def tick_from_sqrt_price_x96(sqrt_price_x96: int) -> int:
    """Inverse of the above — uses ln to find tick."""
    sqrt_price = Decimal(sqrt_price_x96) / Q96
    price = sqrt_price * sqrt_price
    tick = (price.ln() / _LN_BASE)
    return int(tick)


def price_from_tick(tick: int, decimals0: int, decimals1: int) -> Decimal:
    """Return human-readable price as token1/token0 (e.g. WETH per USDC).

    V3 raw price = 1.0001^tick is in raw units; we apply decimal correction
    so the returned value matches a calculator. For USDC (6) / WETH (18) and
    tick ~198,756 the result is ~0.000435 (i.e. 1 USDC ≈ 0.000435 WETH).
    """
    raw_price = Decimal("1.0001") ** Decimal(tick)
    return raw_price * (Decimal(10) ** (decimals0 - decimals1))


def align_tick(tick: int, tick_spacing: int) -> int:
    """Snap tick down to the next valid (spacing-aligned) tick."""
    return (tick // tick_spacing) * tick_spacing


def tick_range_from_pct(
    current_tick: int, lower_pct: float, upper_pct: float, tick_spacing: int
) -> tuple[int, int]:
    """Convert symmetric percentage range (e.g. -10/+10) into aligned tick
    bounds. ±X% in price space → ±ln(1+X/100)/ln(1.0001) in tick space."""
    # Use ln approximation: 1% in price ≈ ln(1.01)/ln(1.0001) ≈ 99.5 ticks.
    delta_lower_ticks = int(
        (Decimal(1 + lower_pct / 100.0).ln() / _LN_BASE)
        if lower_pct > -100 else Decimal(-887272)
    )
    delta_upper_ticks = int(
        (Decimal(1 + upper_pct / 100.0).ln() / _LN_BASE)
        if upper_pct < 10_000 else Decimal(887272)
    )
    raw_lower = current_tick + delta_lower_ticks
    raw_upper = current_tick + delta_upper_ticks
    return align_tick(raw_lower, tick_spacing), align_tick(raw_upper, tick_spacing)


def optimal_ratio_for_range(
    *,
    sqrt_price_x96_current: int,
    tick_lower: int,
    tick_upper: int,
    decimals0: int,
    decimals1: int,
    price_token0_usd: float,
    price_token1_usd: float,
) -> tuple[Decimal, Decimal]:
    """Return (ratio_token0_usd, ratio_token1_usd) summing to 1.

    Below P_lower: 100% token1 (limit order up — price needs to come back
    into range from below in token1 terms).
    Above P_upper: 100% token0.
    Inside range: split per V3 liquidity math.
    """
    sqrt_p_current = Decimal(sqrt_price_x96_current) / Q96
    sqrt_p_lower = (Decimal("1.0001") ** Decimal(tick_lower)).sqrt()
    sqrt_p_upper = (Decimal("1.0001") ** Decimal(tick_upper)).sqrt()

    if sqrt_p_current <= sqrt_p_lower:
        return Decimal(0), Decimal(1)
    if sqrt_p_current >= sqrt_p_upper:
        return Decimal(1), Decimal(0)

    # Pick a notional L=1 and compute physical amounts; convert to USD.
    L = Decimal(1)
    amount0 = L * (sqrt_p_upper - sqrt_p_current) / (sqrt_p_current * sqrt_p_upper)
    amount1 = L * (sqrt_p_current - sqrt_p_lower)

    human0 = amount0 / (Decimal(10) ** decimals0)
    human1 = amount1 / (Decimal(10) ** decimals1)
    usd0 = human0 * Decimal(price_token0_usd)
    usd1 = human1 * Decimal(price_token1_usd)
    total = usd0 + usd1
    if total <= 0:
        return Decimal("0.5"), Decimal("0.5")
    return usd0 / total, usd1 / total


def capital_efficiency(
    *, tick_lower: int, tick_upper: int, current_tick: int
) -> float:
    """Capital efficiency multiplier vs full-range (approx).

    1 / (1 - sqrt(p_lower/p_current))  for the lower half, take min of the
    two halves (since position is symmetric around current).
    """
    if tick_upper <= current_tick or tick_lower >= current_tick:
        return 1.0  # out of range — efficiency irrelevant
    p_lower = Decimal("1.0001") ** Decimal(tick_lower)
    p_upper = Decimal("1.0001") ** Decimal(tick_upper)
    p_current = Decimal("1.0001") ** Decimal(current_tick)
    lower_ratio = float((p_lower / p_current).sqrt())
    upper_ratio = float((p_current / p_upper).sqrt())
    lower_eff = 1.0 / max(1 - lower_ratio, 1e-9)
    upper_eff = 1.0 / max(1 - upper_ratio, 1e-9)
    return min(lower_eff, upper_eff)
