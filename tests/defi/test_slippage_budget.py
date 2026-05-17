"""Pin tests for src.defi.slippage_budget — V7-019.

Locks in the LEG_WEIGHTS schedule and the round + redistribute algorithm so
future tweaks to the weights table don't silently shift per-leg allocations.
"""

from __future__ import annotations

import pytest

from src.defi.slippage_budget import (
    LEG_WEIGHTS,
    split_slippage,
    validate_split,
)


def test_split_three_legs_swap_swap_lp_add_sums_and_lp_heavier() -> None:
    """50 bps / 3 legs → list sums to 50, lp_add ≥ swap (heavier weight)."""
    out = split_slippage(50, ["swap", "swap", "lp_add"])
    assert isinstance(out, list)
    assert len(out) == 3
    assert sum(out) == 50
    # lp_add (index 2) has weight 1.3 vs swap 1.0 → must receive ≥ either swap.
    assert out[2] >= out[0]
    assert out[2] >= out[1]


def test_split_even_two_swaps_is_30_30() -> None:
    """Two equal-weight legs split a clean 60 bps exactly evenly."""
    assert split_slippage(60, ["swap", "swap"]) == [30, 30]


def test_split_single_leg_gets_full_budget() -> None:
    """One leg → that leg gets the entire budget."""
    assert split_slippage(100, ["swap"]) == [100]


def test_split_bridge_swap_lp_add_bridge_gets_largest_share() -> None:
    """Bridge (weight 1.5) outweighs lp_add (1.3) and swap (1.0)."""
    out = split_slippage(50, ["bridge", "swap", "lp_add"])
    assert len(out) == 3
    assert sum(out) == 50
    # Bridge is at index 0, has the highest weight → strictly largest share.
    assert out[0] > out[1]
    assert out[0] > out[2]
    # And lp_add should still beat plain swap.
    assert out[2] >= out[1]


def test_validate_split_happy_path() -> None:
    """A clean [15, 15, 20] / 50 split passes validation."""
    assert validate_split([15, 15, 20], 50) is True


def test_validate_split_rejects_sum_mismatch() -> None:
    """Sum != total_bps → reject."""
    assert validate_split([15, 15, 21], 50) is False


def test_validate_split_rejects_leg_below_min() -> None:
    """Any leg below min_per_leg → reject even if the sum matches."""
    assert validate_split([1, 24, 25], 50, min_per_leg=5) is False


def test_leg_weights_table_pinned() -> None:
    """Pin the canonical weight table — heavier-impact legs > swaps."""
    assert LEG_WEIGHTS["swap"] == 1.0
    assert LEG_WEIGHTS["bridge"] == 1.5
    assert LEG_WEIGHTS["lp_add"] == 1.3
    assert LEG_WEIGHTS["lp_increase"] == 1.3
    assert LEG_WEIGHTS["stake"] == 0.5
    assert LEG_WEIGHTS["supply"] == 0.5


def test_split_unknown_leg_kind_defaults_to_swap_weight() -> None:
    """Unknown leg kind falls back to weight 1.0 (treated like a swap)."""
    out = split_slippage(60, ["swap", "mystery_leg"])
    assert sum(out) == 60
    # Equal weights → equal split.
    assert out == [30, 30]


def test_split_empty_leg_list_raises() -> None:
    """An empty leg list is a programmer error."""
    with pytest.raises(ValueError):
        split_slippage(50, [])


def test_split_always_sums_exactly_across_a_range() -> None:
    """Property-ish sanity: sum invariant holds across many budget values."""
    kinds = ["swap", "bridge", "lp_add", "stake", "supply"]
    for total in range(10, 501, 7):
        out = split_slippage(total, kinds)
        assert sum(out) == total, f"sum mismatch for total={total}: {out}"
        assert len(out) == len(kinds)
