"""Pin tests for the pair-category fee-tier default resolver (V7-017).

Spec §3 — when no fee tier is specified for a V3-style concentrated-liquidity
pool, the default tier is chosen from the pair category:

    stable/stable -> 100  (1 bp)
    stable/blue   -> 500  (5 bp)
    blue/blue     -> 3000 (30 bp)
    exotic        -> 10000 (100 bp)
"""

from __future__ import annotations

import pytest

from src.defi.fee_tier_defaults import (
    BLUE_TOKENS,
    STABLE_TOKENS,
    categorize_pair,
    default_fee_tier,
)


# --------------------------------------------------------------------------- #
# default_fee_tier — the spec-mandated pin values                             #
# --------------------------------------------------------------------------- #


def test_stable_stable_defaults_to_1bp() -> None:
    assert default_fee_tier("USDC", "USDT") == 100


def test_stable_blue_defaults_to_5bp() -> None:
    assert default_fee_tier("USDC", "WETH") == 500


def test_blue_blue_defaults_to_30bp() -> None:
    assert default_fee_tier("WETH", "WBTC") == 3000


def test_exotic_with_one_blue_defaults_to_100bp() -> None:
    # PEPE is not in either set -> exotic regardless of WETH on the other side.
    assert default_fee_tier("PEPE", "WETH") == 10000


def test_two_exotics_default_to_100bp() -> None:
    assert default_fee_tier("PEPE", "DOGE") == 10000


def test_default_fee_tier_is_case_insensitive() -> None:
    # Bridge-suffix stable + lower-case canonical stable should still map
    # to the stable/stable tier.
    assert default_fee_tier("usdc.e", "usdt") == 100


# --------------------------------------------------------------------------- #
# categorize_pair — exhaustive coverage of the four enum branches             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("t0", "t1", "expected"),
    [
        ("USDC", "USDT", "stable_stable"),
        ("DAI", "FRAX", "stable_stable"),
        ("USDC", "WETH", "stable_blue"),
        ("WBTC", "USDT", "stable_blue"),
        ("WETH", "WBTC", "blue_blue"),
        ("STETH", "WETH", "blue_blue"),
        ("PEPE", "WETH", "exotic"),
        ("PEPE", "DOGE", "exotic"),
        ("SHIB", "USDC", "exotic"),  # exotic + stable is still exotic per spec
    ],
)
def test_categorize_pair_enum_branches(t0: str, t1: str, expected: str) -> None:
    assert categorize_pair(t0, t1) == expected


def test_categorize_pair_is_case_insensitive() -> None:
    assert categorize_pair("usdc", "usdt") == "stable_stable"
    assert categorize_pair("weth", "wbtc") == "blue_blue"
    assert categorize_pair("USDC.e", "WETH") == "stable_blue"


def test_categorize_pair_is_order_independent() -> None:
    assert categorize_pair("USDC", "WETH") == categorize_pair("WETH", "USDC")
    assert categorize_pair("PEPE", "USDC") == categorize_pair("USDC", "PEPE")


# --------------------------------------------------------------------------- #
# Set-membership sanity (guards against accidental edits to the token sets)   #
# --------------------------------------------------------------------------- #


def test_stable_set_contains_canonical_members() -> None:
    for sym in ("USDC", "USDT", "DAI", "FRAX", "USDC.E", "USDT.E"):
        assert sym in STABLE_TOKENS


def test_blue_set_contains_canonical_members() -> None:
    for sym in ("WETH", "ETH", "WBTC", "BTC", "STETH", "WSTETH"):
        assert sym in BLUE_TOKENS


def test_stable_and_blue_sets_are_disjoint() -> None:
    assert STABLE_TOKENS.isdisjoint(BLUE_TOKENS)
