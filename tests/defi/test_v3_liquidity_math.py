"""V7 §1 — pin tests for Uniswap V3 SDK-exact liquidity math."""
from __future__ import annotations

from src.defi.math.v3_liquidity import (
    Q96,
    get_liquidity_for_amount0,
    get_liquidity_for_amount1,
    get_amount0_for_liquidity,
    get_amount1_for_liquidity,
)


# Known fixture: USDC (6 dec) / WETH (18 dec) at ETH ≈ $3000.
# sqrt(3000 * 1e12) ≈ 1732050 (price scaled).
# Test values picked for arithmetic transparency.
SQRT_A = 1_000 * Q96  # sqrt(price) = 1000
SQRT_B = 2_000 * Q96  # sqrt(price) = 2000


def test_q96_constant():
    assert Q96 == 2 ** 96


def test_liquidity_for_amount0_basic():
    # L = amount0 * sqrtA * sqrtB / (sqrtB - sqrtA)
    # With sqrtA=1000*Q96, sqrtB=2000*Q96, intermediate = sqrtA*sqrtB/Q96 = 1000*2000*Q96
    # liquidity = amount0 * 2_000_000 * Q96 / (1000*Q96) = amount0 * 2_000_000 / 1
    # wait: (hi - lo) = 1000*Q96, so liquidity = amount0 * 2_000_000 * Q96 / (1000*Q96) = amount0 * 2000
    L = get_liquidity_for_amount0(SQRT_A, SQRT_B, amount0=1_000_000)
    assert L == 2_000_000_000  # 1_000_000 * 2_000


def test_liquidity_for_amount1_basic():
    # L = amount1 * Q96 / (sqrtB - sqrtA), where (sqrtB - sqrtA) = 1000*Q96
    # So L = amount1 / 1000
    L = get_liquidity_for_amount1(SQRT_A, SQRT_B, amount1=5_000_000)
    assert L == 5_000  # 5_000_000 / 1000


def test_amount0_for_liquidity_roundtrip():
    L = get_liquidity_for_amount0(SQRT_A, SQRT_B, amount0=1_000_000)
    a0 = get_amount0_for_liquidity(SQRT_A, SQRT_B, L)
    # Allow off-by-1 from integer floor div.
    assert abs(a0 - 1_000_000) <= 1


def test_amount1_for_liquidity_roundtrip():
    L = get_liquidity_for_amount1(SQRT_A, SQRT_B, amount1=5_000_000)
    a1 = get_amount1_for_liquidity(SQRT_A, SQRT_B, L)
    assert abs(a1 - 5_000_000) <= 1


def test_ordered_args_swappable():
    L_a = get_liquidity_for_amount0(SQRT_A, SQRT_B, 1000)
    L_b = get_liquidity_for_amount0(SQRT_B, SQRT_A, 1000)
    assert L_a == L_b


def test_zero_range_returns_zero():
    assert get_liquidity_for_amount0(SQRT_A, SQRT_A, 1000) == 0
    assert get_liquidity_for_amount1(SQRT_A, SQRT_A, 1000) == 0
    assert get_amount0_for_liquidity(SQRT_A, SQRT_A, 1000) == 0
    assert get_amount1_for_liquidity(SQRT_A, SQRT_A, 1000) == 0
