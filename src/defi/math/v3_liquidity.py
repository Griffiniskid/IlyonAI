"""V7 §1 gap — Uniswap V3 SDK-exact liquidity math (Q96 fixed-point).

Canonical formulas from `LiquidityAmounts.sol` / `@uniswap/v3-sdk`. All
inputs are integer wei / sqrtPriceX96 values; outputs are integer
liquidity / wei units. Uses Python's arbitrary-precision int so there
is no overflow risk; Q96 = 2**96.
"""
from __future__ import annotations


__all__ = [
    "Q96",
    "get_liquidity_for_amount0",
    "get_liquidity_for_amount1",
    "get_amount0_for_liquidity",
    "get_amount1_for_liquidity",
]


Q96: int = 1 << 96


def _ordered(a: int, b: int) -> tuple[int, int]:
    """Return (lower, upper) sqrtPriceX96 — Uniswap convention."""
    return (a, b) if a <= b else (b, a)


def get_liquidity_for_amount0(
    sqrt_price_lower_x96: int,
    sqrt_price_upper_x96: int,
    amount0: int,
) -> int:
    """L = amount0 * (sqrtA * sqrtB) / (sqrtB - sqrtA), all in Q96."""
    lo, hi = _ordered(sqrt_price_lower_x96, sqrt_price_upper_x96)
    if hi == lo:
        return 0
    intermediate = (lo * hi) // Q96
    return (amount0 * intermediate) // (hi - lo)


def get_liquidity_for_amount1(
    sqrt_price_lower_x96: int,
    sqrt_price_upper_x96: int,
    amount1: int,
) -> int:
    """L = amount1 / (sqrtB - sqrtA), result in Q96."""
    lo, hi = _ordered(sqrt_price_lower_x96, sqrt_price_upper_x96)
    if hi == lo:
        return 0
    return (amount1 * Q96) // (hi - lo)


def get_amount0_for_liquidity(
    sqrt_price_lower_x96: int,
    sqrt_price_upper_x96: int,
    liquidity: int,
) -> int:
    """amount0 = L * (sqrtB - sqrtA) / (sqrtA * sqrtB) * Q96."""
    lo, hi = _ordered(sqrt_price_lower_x96, sqrt_price_upper_x96)
    if hi == lo or lo == 0:
        return 0
    numerator = (liquidity << 96) * (hi - lo)
    denominator = hi * lo
    return numerator // denominator


def get_amount1_for_liquidity(
    sqrt_price_lower_x96: int,
    sqrt_price_upper_x96: int,
    liquidity: int,
) -> int:
    """amount1 = L * (sqrtB - sqrtA)."""
    lo, hi = _ordered(sqrt_price_lower_x96, sqrt_price_upper_x96)
    if hi == lo:
        return 0
    return (liquidity * (hi - lo)) // Q96
