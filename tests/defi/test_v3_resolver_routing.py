"""Regression tests for v3_pool_resolver protocol routing.

Spec §6a + §8: Slipstream / Velodrome CL keep their own factory + NFPM
addresses distinct from Uniswap V3's. A pre-resolver "proto normalisation"
that collapsed every CL-class protocol to "uniswap-v3" caused Velodrome
CL pools to mint to Uniswap's NFPM instead of Velodrome's — silently
breaking the receipt path.

This test asserts the V3_FACTORIES table has the correct, NON-Uniswap
addresses for tickSpacing-keyed forks so any regression that drops the
mapping fails at unit-test time.
"""
from __future__ import annotations

from src.data.v3_pool_resolver import (
    SLIPSTREAM_FEE_TO_TICK_SPACING,
    V3_FACTORIES,
    _TICKSPACING_KEYED_PROTOCOLS,
)

UNISWAP_V3_NFPM = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"


def test_slipstream_base_factory_distinct_from_uniswap():
    cfg = V3_FACTORIES[("base", "aerodrome-slipstream")]
    assert cfg["factory"].lower() != "0x33128a8fc17869897dce68ed026d694621f6fdfd"  # Uniswap V3 Base factory
    assert cfg["nfp_manager"].lower() != UNISWAP_V3_NFPM.lower()
    assert cfg["factory"].startswith("0x")
    assert cfg["nfp_manager"].startswith("0x")


def test_velodrome_cl_optimism_factory_distinct_from_uniswap():
    cfg = V3_FACTORIES[("optimism", "velodrome-cl")]
    # Velodrome CL Optimism NFPM = 0x416b433906b1B72FA758e166e239c43d68dC6F29
    assert cfg["nfp_manager"].lower() == "0x416b433906b1b72fa758e166e239c43d68dc6f29"
    assert cfg["nfp_manager"].lower() != UNISWAP_V3_NFPM.lower()


def test_velodrome_slipstream_alias_maps_same_addresses():
    cl = V3_FACTORIES[("optimism", "velodrome-cl")]
    slip = V3_FACTORIES[("optimism", "velodrome-slipstream")]
    assert cl == slip


def test_tickspacing_keyed_protocols_set():
    # Slipstream + Velodrome CL key by tickSpacing not fee. Spec §6a.
    expected = {"aerodrome-slipstream", "velodrome-cl", "velodrome-slipstream"}
    assert _TICKSPACING_KEYED_PROTOCOLS == frozenset(expected)


def test_slipstream_fee_to_tick_spacing_covers_common_tiers():
    # Common Slipstream tickSpacings on Base: 1, 50, 100, 200, 2000.
    spacings = set(SLIPSTREAM_FEE_TO_TICK_SPACING.values())
    for ts in {1, 50, 100, 200, 2000}:
        assert ts in spacings, f"tickSpacing {ts} not in resolver map"


def test_pancakeswap_v3_uses_uniswap_v3_nfpm_universal():
    # PancakeSwap V3 deploys its own NFPM (not Uniswap's). Sanity that
    # the table doesn't accidentally point to Uniswap's address.
    bsc = V3_FACTORIES[("bsc", "pancakeswap-v3")]
    assert bsc["nfp_manager"].lower() != UNISWAP_V3_NFPM.lower()
    eth = V3_FACTORIES[("ethereum", "pancakeswap-v3")]
    assert eth["nfp_manager"].lower() != UNISWAP_V3_NFPM.lower()


def test_uniswap_v3_uses_canonical_nfpm_on_optimism():
    cfg = V3_FACTORIES[("optimism", "uniswap-v3")]
    assert cfg["nfp_manager"].lower() == UNISWAP_V3_NFPM.lower()


def test_uniswap_v3_uses_canonical_nfpm_on_arbitrum():
    cfg = V3_FACTORIES[("arbitrum", "uniswap-v3")]
    assert cfg["nfp_manager"].lower() == UNISWAP_V3_NFPM.lower()


def test_base_uniswap_v3_has_distinct_addresses():
    # Base Uniswap V3 deployment differs from Eth/Arb/Optimism — Base
    # uses its own factory + NFPM. Catches a copy-paste regression.
    cfg = V3_FACTORIES[("base", "uniswap-v3")]
    assert cfg["factory"].lower() != "0x1f98431c8ad98523631ae4a59f267346ea31f984"
    assert cfg["nfp_manager"].lower() != UNISWAP_V3_NFPM.lower()
