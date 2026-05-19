"""Pin tests for spec per-leg slippage split.

Spec: cross-chain or multi-step plans split a single 50bp slippage budget
across legs: 15 bps swap_src + 15 bps bridge + 20 bps swap_dst. Stable-only
legs may use 10 bps total. Each leg is floored at 10 bps so the aggregator
never receives a 0-bps tolerance window.
"""
from __future__ import annotations

from src.defi.execution.slippage_split import (
    DEFAULT_SPLIT_BPS,
    SLIPPAGE_FLOOR_BPS,
    slippage_for_leg,
    split_total_budget,
)


def test_default_swap_src_is_15_bps():
    assert slippage_for_leg("swap_src") == 15


def test_default_bridge_is_15_bps():
    assert slippage_for_leg("bridge") == 15


def test_default_swap_dst_is_20_bps():
    assert slippage_for_leg("swap_dst") == 20


def test_default_stable_pair_is_10_bps():
    assert slippage_for_leg("stable_pair") == 10


def test_default_single_leg_is_50_bps():
    assert slippage_for_leg("single_leg") == 50


def test_override_above_floor_wins():
    assert slippage_for_leg("swap_src", override=30) == 30
    assert slippage_for_leg("bridge", override=75) == 75
    assert slippage_for_leg("swap_dst", override=100) == 100


def test_override_below_floor_clamped_to_floor():
    assert slippage_for_leg("swap_src", override=2) == SLIPPAGE_FLOOR_BPS
    assert SLIPPAGE_FLOOR_BPS == 10
    assert slippage_for_leg("bridge", override=0) == SLIPPAGE_FLOOR_BPS
    assert slippage_for_leg("swap_dst", override=-5) == SLIPPAGE_FLOOR_BPS


def test_split_total_budget_50_matches_default():
    """50 bps across [swap_src, bridge, swap_dst] should distribute roughly
    [15, 15, 20] — the canonical spec split."""
    result = split_total_budget(50, ["swap_src", "bridge", "swap_dst"])
    # Weights 15:15:20 sum to 50, total_bps=50 → exact proportions back.
    assert result == [15, 15, 20]


def test_split_total_budget_100_doubles_each_leg():
    """A 100 bps user override across the same three legs doubles each
    leg's share — 30:30:40."""
    result = split_total_budget(100, ["swap_src", "bridge", "swap_dst"])
    assert result == [30, 30, 40]


def test_split_total_budget_empty_returns_empty():
    assert split_total_budget(50, []) == []


def test_split_total_budget_respects_floor():
    """Tiny total budget must still floor each leg at SLIPPAGE_FLOOR_BPS so
    aggregator legs never receive a 0-bps tolerance window."""
    result = split_total_budget(5, ["swap_src", "bridge", "swap_dst"])
    assert all(b >= SLIPPAGE_FLOOR_BPS for b in result)
    assert len(result) == 3


def test_default_split_bps_constants_intact():
    """Pin the spec table — these numbers are referenced verbatim in
    docs/SPEC_COVERAGE.md and on-chain aggregator integration tests."""
    assert DEFAULT_SPLIT_BPS["swap_src"] == 15
    assert DEFAULT_SPLIT_BPS["bridge"] == 15
    assert DEFAULT_SPLIT_BPS["swap_dst"] == 20
    assert DEFAULT_SPLIT_BPS["stable_pair"] == 10
    assert DEFAULT_SPLIT_BPS["single_leg"] == 50
    assert SLIPPAGE_FLOOR_BPS == 10
