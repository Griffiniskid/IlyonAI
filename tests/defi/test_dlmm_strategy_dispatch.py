"""V7-014 — pin tests for LpStrategy → DLMM bin distribution dispatch.

Ensures every member of :class:`LpStrategy` is mapped:

* SPOT / CURVE / BID_ASK route to their bin-distribution functions and
  return a normalised dict (sums to ~1.0, spans the right bin range).
* MAVERICK_STATIC / MAVERICK_RIGHT / MAVERICK_LEFT / MAVERICK_BOTH
  raise ``NotImplementedError`` with a message that mentions Maverick.
* The loop test (``test_every_enum_value_is_handled``) iterates the
  whole enum so that any future addition that is NOT wired into
  ``dispatch_strategy`` causes this suite to fail loudly. This is the
  spec-compliance gate — every enum value must map to a function.
"""
from __future__ import annotations

import math

import pytest

from src.agent.intent.liquidity_intent import LpStrategy
from src.defi.dlmm.bin_distribution import (
    bid_ask_distribution,
    curve_distribution,
    dispatch_strategy,
    spot_distribution,
)


SUPPORTED_STRATEGIES = (
    LpStrategy.SPOT,
    LpStrategy.CURVE,
    LpStrategy.BID_ASK,
)

MAVERICK_STRATEGIES = (
    LpStrategy.MAVERICK_STATIC,
    LpStrategy.MAVERICK_RIGHT,
    LpStrategy.MAVERICK_LEFT,
    LpStrategy.MAVERICK_BOTH,
)


# ---------------------------------------------------------------------------
# 1. SPOT / CURVE / BID_ASK — dict shape + bin span + weight sum.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", SUPPORTED_STRATEGIES)
def test_supported_strategy_returns_normalised_dict(strategy: LpStrategy):
    active_bin = 10
    range_bins = 5

    result = dispatch_strategy(strategy, active_bin=active_bin, range_bins=range_bins)

    assert isinstance(result, dict)
    # Bin span = 2 * range_bins + 1, centered on active_bin.
    expected_indices = set(range(active_bin - range_bins, active_bin + range_bins + 1))
    assert set(result.keys()) == expected_indices
    assert len(result) == 2 * range_bins + 1
    # Weights sum to ~1.0 with floating-point epsilon (bid_ask uses 1e-6
    # floor at center, so allow a slightly looser tol for that one).
    assert math.isclose(sum(result.values()), 1.0, rel_tol=1e-6, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# 2. MAVERICK_* — must raise NotImplementedError mentioning "Maverick".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", MAVERICK_STRATEGIES)
def test_maverick_strategies_raise_not_implemented(strategy: LpStrategy):
    with pytest.raises(NotImplementedError) as exc_info:
        dispatch_strategy(strategy, 10, 5)
    assert "Maverick" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. Identity — dispatch_strategy is a router, not a re-computation.
# ---------------------------------------------------------------------------


def test_dispatch_spot_is_identity_to_spot_distribution():
    active_bin, range_bins = 10, 5
    via_dispatch = dispatch_strategy(LpStrategy.SPOT, active_bin, range_bins)
    direct = spot_distribution(active_bin, range_bins)
    assert via_dispatch == direct


def test_dispatch_curve_is_identity_to_curve_distribution():
    active_bin, range_bins = 10, 5
    via_dispatch = dispatch_strategy(LpStrategy.CURVE, active_bin, range_bins)
    direct = curve_distribution(active_bin, range_bins)
    assert via_dispatch == direct


def test_dispatch_bid_ask_is_identity_to_bid_ask_distribution():
    active_bin, range_bins = 10, 5
    via_dispatch = dispatch_strategy(LpStrategy.BID_ASK, active_bin, range_bins)
    direct = bid_ask_distribution(active_bin, range_bins)
    assert via_dispatch == direct


# ---------------------------------------------------------------------------
# 4. Spec-compliance loop — every LpStrategy member must be handled.
#
# If a future enum value is added that is NOT mapped in dispatch_strategy,
# the catch-all branch in dispatch_strategy raises ValueError, which is
# NOT caught here — so this test fails loudly. That is intentional: any
# new LpStrategy member must be wired into the dispatcher.
# ---------------------------------------------------------------------------


def test_every_enum_value_is_handled():
    """Every member of LpStrategy either returns a dict or raises NotImplementedError."""
    unhandled: list[LpStrategy] = []
    for strategy in LpStrategy:
        try:
            result = dispatch_strategy(strategy, active_bin=10, range_bins=5)
        except NotImplementedError:
            # Acceptable — Maverick path, explicitly stubbed.
            continue
        else:
            if not isinstance(result, dict):
                unhandled.append(strategy)
    assert unhandled == [], (
        f"LpStrategy values returned non-dict from dispatch_strategy: {unhandled}"
    )
    # Sanity — confirm we actually iterated all 7 members the spec defines.
    assert len(list(LpStrategy)) == 7, (
        "LpStrategy member count changed — review dispatch_strategy mapping "
        "and update this pin test accordingly."
    )
