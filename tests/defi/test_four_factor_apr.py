"""Spec §6e — four-factor APR composition pin tests.

Closes the audit gap: empirical P_in is real but CE / fee_yield_full / IL_drag
closed-forms were not assembled. This pin file locks the contract:

  APR(width) = P_in(width) * CE(width) * fee_yield_full(pool) - IL_drag(width, vol)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.defi.apr_curve.four_factor import (  # noqa: E402
    FourFactorAPRPoint,
    capital_efficiency,
    compose_apr_curve,
    fee_yield_full,
    il_drag,
)


# ---------------------------------------------------------------------------
# capital_efficiency
# ---------------------------------------------------------------------------


def test_capital_efficiency_orders_tight_above_wide_above_full() -> None:
    ce_tight = capital_efficiency(500)       # +/-5%
    ce_balanced = capital_efficiency(1000)   # +/-10%
    ce_wide = capital_efficiency(2500)       # +/-25%
    ce_full = capital_efficiency(10000)      # full range
    assert ce_tight > ce_balanced > ce_wide > ce_full


def test_capital_efficiency_full_range_equals_one() -> None:
    """A width that spans the entire range (>=10000 bps) collapses to CE=1.0."""
    assert capital_efficiency(10000) == pytest.approx(1.0)
    assert capital_efficiency(20000) == pytest.approx(1.0)


def test_capital_efficiency_zero_or_negative_width_safe() -> None:
    """Degenerate width inputs must NOT raise and must return a sane CE=1.0."""
    assert capital_efficiency(0) == 1.0
    assert capital_efficiency(-100) == 1.0


# ---------------------------------------------------------------------------
# fee_yield_full
# ---------------------------------------------------------------------------


def test_fee_yield_full_handles_none() -> None:
    assert fee_yield_full(None) == 0.0


def test_fee_yield_full_clamps_negative() -> None:
    """Negative fee APR from upstream feeds collapses to zero, never negative."""
    assert fee_yield_full(-0.05) == 0.0


def test_fee_yield_full_passes_through_positive() -> None:
    assert fee_yield_full(0.15) == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# il_drag
# ---------------------------------------------------------------------------


def test_il_drag_rises_with_vol() -> None:
    low = il_drag(1000, 0.2)
    high = il_drag(1000, 0.8)
    assert high > low


def test_il_drag_rises_with_width() -> None:
    narrow = il_drag(500, 0.5)
    wide = il_drag(2500, 0.5)
    assert wide > narrow


def test_il_drag_zero_when_vol_or_width_zero() -> None:
    assert il_drag(1000, 0.0) == 0.0
    assert il_drag(0, 0.5) == 0.0
    assert il_drag(-100, 0.5) == 0.0
    assert il_drag(1000, -0.1) == 0.0


# ---------------------------------------------------------------------------
# compose_apr_curve
# ---------------------------------------------------------------------------


def test_compose_tight_with_low_vol_beats_full_range() -> None:
    """Spec §6e payoff: a tight range with low vol earns more than full range.

    Tight = +/-5% with 95% in-range probability and low vol (0.05).
    Full = +/-100% with 100% in-range and same low vol.
    Concentrated CE should make tight > full when IL is small.
    """
    pool_fee = 0.20  # 20% annualized fee/TVL
    vol = 0.05
    p_in = [0.95, 1.00]
    widths = [500, 10000]
    composed = compose_apr_curve(p_in, widths, pool_fee, vol)
    assert composed[0] > composed[1]


def test_compose_high_vol_crushes_composed_apr() -> None:
    """When vol is huge, IL_drag dominates and composed APR collapses to ~0."""
    pool_fee = 0.05
    p_in = [0.40]
    widths = [2500]
    low_vol = compose_apr_curve(p_in, widths, pool_fee, 0.1)
    high_vol = compose_apr_curve(p_in, widths, pool_fee, 5.0)
    assert high_vol[0] < low_vol[0]
    # High vol with wide range and modest fee should clamp to zero floor.
    assert high_vol[0] == 0.0


def test_compose_empty_inputs_returns_empty_output() -> None:
    assert compose_apr_curve([], [], 0.1, 0.2) == []


def test_compose_falls_back_when_fee_apr_missing() -> None:
    """No pool fee data -> composed APR is zero (P_in * CE * 0 - IL_drag, clamped)."""
    p_in = [0.95]
    widths = [500]
    composed = compose_apr_curve(p_in, widths, None, 0.1)
    assert composed[0] == 0.0


def test_compose_never_negative() -> None:
    """Even pathological inputs (huge IL, tiny fee) clamp at zero."""
    p_in = [0.5, 0.5, 0.5]
    widths = [500, 2500, 10000]
    composed = compose_apr_curve(p_in, widths, 0.001, 10.0)
    assert all(x >= 0.0 for x in composed)


# ---------------------------------------------------------------------------
# FourFactorAPRPoint dataclass exists and is frozen
# ---------------------------------------------------------------------------


def test_four_factor_apr_point_dataclass_frozen() -> None:
    pt = FourFactorAPRPoint(
        width_bps=1000, p_in=0.9, ce=4.0, fee_yield=0.15, il_drag=0.001,
        composed_apr=0.539,
    )
    assert pt.width_bps == 1000
    assert pt.composed_apr == pytest.approx(0.539)
    with pytest.raises(Exception):  # FrozenInstanceError subclasses AttributeError
        pt.width_bps = 2000  # type: ignore[misc]
