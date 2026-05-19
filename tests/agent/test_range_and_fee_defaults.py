"""Pin tests for spec §3 LP range + fee-tier defaults.

Two spec gaps closed:

§3.3 — "Stable pairs use ±0.5% / ±0.1% / ±0.05%."
       Blue-chip pairs continue to use ±25% / ±10% / ±5%.

§3.2 — "stable/stable → 1bp; blue-chip/blue-chip → 5bp or 30bp;
        exotic → 100bp." Mapped to canonical Uniswap-V3 tiers
        (100 / 500 / 3000 / 10000).
"""

from __future__ import annotations

import pytest

from src.agent.intent.liquidity_intent import (
    RANGE_PRESET_BPS,
    STABLE_RANGE_PRESET_BPS,
    RangePreset,
    is_stable_pair,
    range_preset_bps,
)
from src.defi.fee_tier_defaults import (
    default_fee_tier,
    default_fee_tier_for_pair,
)


# --------------------------------------------------------------------------- #
# §3.3 — STABLE_RANGE_PRESET_BPS pin values                                   #
# --------------------------------------------------------------------------- #


def test_stable_range_preset_bps_wide_is_50_bps() -> None:
    """Spec §3.3: stable WIDE = ±0.5% = 50 bps."""
    assert STABLE_RANGE_PRESET_BPS[RangePreset.WIDE] == 50


def test_stable_range_preset_bps_balanced_is_10_bps() -> None:
    """Spec §3.3: stable BALANCED = ±0.1% = 10 bps."""
    assert STABLE_RANGE_PRESET_BPS[RangePreset.BALANCED] == 10


def test_stable_range_preset_bps_tight_is_5_bps() -> None:
    """Spec §3.3: stable TIGHT = ±0.05% = 5 bps."""
    assert STABLE_RANGE_PRESET_BPS[RangePreset.TIGHT] == 5


def test_stable_range_preset_bps_full_is_none() -> None:
    assert STABLE_RANGE_PRESET_BPS[RangePreset.FULL] is None


def test_stable_range_preset_bps_customs_are_none() -> None:
    assert STABLE_RANGE_PRESET_BPS[RangePreset.CUSTOM_TICKS] is None
    assert STABLE_RANGE_PRESET_BPS[RangePreset.CUSTOM_PRICE] is None


def test_stable_range_preset_bps_covers_full_enum() -> None:
    """All RangePreset values must appear in the stable table."""
    assert set(STABLE_RANGE_PRESET_BPS.keys()) == set(RangePreset)


def test_stable_presets_are_strictly_narrower_than_bluechip() -> None:
    """Sanity: every non-None stable preset must be << its blue-chip twin."""
    for preset in (RangePreset.WIDE, RangePreset.BALANCED, RangePreset.TIGHT):
        stable = STABLE_RANGE_PRESET_BPS[preset]
        blue = RANGE_PRESET_BPS[preset]
        assert stable is not None and blue is not None
        # Stable bands are at least 50× tighter (e.g. 2500 → 50, 500 → 5).
        assert stable * 50 <= blue, (
            f"{preset.name}: stable={stable} bps vs blue-chip={blue} bps"
        )


# --------------------------------------------------------------------------- #
# range_preset_bps() — selector helper                                        #
# --------------------------------------------------------------------------- #


def test_range_preset_bps_default_returns_bluechip_table() -> None:
    """Backward-compat: default is_stable_pair=False → ±25% / ±10% / ±5%."""
    assert range_preset_bps(RangePreset.WIDE) == 2500
    assert range_preset_bps(RangePreset.BALANCED) == 1000
    assert range_preset_bps(RangePreset.TIGHT) == 500


def test_range_preset_bps_stable_flag_returns_stable_table() -> None:
    assert range_preset_bps(RangePreset.WIDE, is_stable_pair=True) == 50
    assert range_preset_bps(RangePreset.BALANCED, is_stable_pair=True) == 10
    assert range_preset_bps(RangePreset.TIGHT, is_stable_pair=True) == 5


def test_range_preset_bps_full_is_none_regardless_of_flag() -> None:
    assert range_preset_bps(RangePreset.FULL) is None
    assert range_preset_bps(RangePreset.FULL, is_stable_pair=True) is None


def test_range_preset_bps_custom_is_none_regardless_of_flag() -> None:
    assert range_preset_bps(RangePreset.CUSTOM_TICKS) is None
    assert range_preset_bps(RangePreset.CUSTOM_PRICE) is None
    assert range_preset_bps(RangePreset.CUSTOM_TICKS, is_stable_pair=True) is None
    assert range_preset_bps(RangePreset.CUSTOM_PRICE, is_stable_pair=True) is None


# --------------------------------------------------------------------------- #
# is_stable_pair() — pair classifier                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("t0", "t1"),
    [
        ("USDC", "USDT"),
        ("DAI", "USDC"),
        ("USDS", "USDC"),
        ("USDE", "USDC"),
        ("usdc", "usdt"),          # case-insensitive
        ("USDC.e", "USDT"),         # bridge variant
    ],
)
def test_is_stable_pair_true_for_stable_stable(t0: str, t1: str) -> None:
    assert is_stable_pair(t0, t1) is True


@pytest.mark.parametrize(
    ("t0", "t1"),
    [
        ("USDC", "WETH"),
        ("WETH", "WBTC"),
        ("PEPE", "USDC"),
        ("PEPE", "DOGE"),
        ("WETH", "ETH"),
    ],
)
def test_is_stable_pair_false_for_non_stable_stable(t0: str, t1: str) -> None:
    assert is_stable_pair(t0, t1) is False


def test_is_stable_pair_none_inputs_are_false() -> None:
    assert is_stable_pair(None, "USDC") is False
    assert is_stable_pair("USDC", None) is False
    assert is_stable_pair(None, None) is False
    assert is_stable_pair("", "USDC") is False


# --------------------------------------------------------------------------- #
# §3.2 — default_fee_tier_for_pair canonical spec name                        #
# --------------------------------------------------------------------------- #


def test_default_fee_tier_for_pair_stable_stable_is_100() -> None:
    """Spec §3.2: stable/stable → 1 bp (V3 tier 100)."""
    assert default_fee_tier_for_pair("USDC", "USDT") == 100


def test_default_fee_tier_for_pair_stable_blue_is_500() -> None:
    """Spec §3.2: stable + blue-chip → 5 bp (V3 tier 500)."""
    assert default_fee_tier_for_pair("USDC", "WETH") == 500


def test_default_fee_tier_for_pair_blue_blue_is_3000() -> None:
    """Spec §3.2: blue-chip/blue-chip → 30 bp (V3 tier 3000)."""
    assert default_fee_tier_for_pair("WETH", "WBTC") == 3000


def test_default_fee_tier_for_pair_exotic_is_10000() -> None:
    """Spec §3.2: exotic → 100 bp (V3 tier 10000)."""
    assert default_fee_tier_for_pair("PEPE", "DOGE") == 10000


def test_default_fee_tier_for_pair_is_alias_of_default_fee_tier() -> None:
    """Both names must agree on every category."""
    for t0, t1 in [
        ("USDC", "USDT"),
        ("USDC", "WETH"),
        ("WETH", "WBTC"),
        ("PEPE", "DOGE"),
        ("SHIB", "USDC"),
    ]:
        assert default_fee_tier_for_pair(t0, t1) == default_fee_tier(t0, t1)


def test_default_fee_tier_returns_only_canonical_v3_tiers() -> None:
    """V3 only supports 100 / 500 / 3000 / 10000."""
    canonical = {100, 500, 3000, 10000}
    for t0, t1 in [
        ("USDC", "USDT"),
        ("USDC", "WETH"),
        ("WETH", "WBTC"),
        ("PEPE", "WETH"),
        ("PEPE", "DOGE"),
        ("SHIB", "USDC"),
    ]:
        assert default_fee_tier_for_pair(t0, t1) in canonical


# --------------------------------------------------------------------------- #
# End-to-end: stable-pair LP uses the narrow band by default                  #
# --------------------------------------------------------------------------- #


def test_usdc_usdt_wide_lp_is_50_bps_not_2500() -> None:
    """Regression guard: USDC/USDT WIDE must be ±0.5%, not ±25%."""
    stable = is_stable_pair("USDC", "USDT")
    assert stable is True
    assert range_preset_bps(RangePreset.WIDE, is_stable_pair=stable) == 50


def test_weth_usdc_wide_lp_is_2500_bps() -> None:
    """Stable + blue-chip is NOT a stable pair → blue-chip presets."""
    stable = is_stable_pair("WETH", "USDC")
    assert stable is False
    assert range_preset_bps(RangePreset.WIDE, is_stable_pair=stable) == 2500
