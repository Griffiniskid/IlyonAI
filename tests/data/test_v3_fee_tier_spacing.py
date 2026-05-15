"""Regression pin for V3 fee_tier → tickSpacing map.

Bricks the resolver if the canonical Uniswap V3 mapping drifts —
catches accidental edits that would mis-encode the mint params.
"""
from __future__ import annotations

from src.data.v3_pool_resolver import (
    FEE_TIER_TICK_SPACING,
    SLIPSTREAM_FEE_TO_TICK_SPACING,
)


def test_uniswap_v3_canonical_fee_tier_spacings():
    """Uniswap V3 canonical mapping per Uniswap docs."""
    assert FEE_TIER_TICK_SPACING == {
        100: 1,      # 0.01%
        500: 10,     # 0.05%
        3000: 60,    # 0.30%
        10000: 200,  # 1.00%
    }


def test_slipstream_fee_tier_spacings_consistent():
    """Slipstream/Velodrome CL — common tickSpacings on Base."""
    # All values are reasonable tick spacings (1-2000).
    for fee, spacing in SLIPSTREAM_FEE_TO_TICK_SPACING.items():
        assert 1 <= spacing <= 2000
        assert 1 <= fee <= 10_000
    # Bricks the regression where fee 1bp (1) maps to anything other than 1.
    assert SLIPSTREAM_FEE_TO_TICK_SPACING[1] == 1
