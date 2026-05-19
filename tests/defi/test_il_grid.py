"""Pin tests for the spec 5-scenario IL grid.

Spec §11 (range planning preview) requires every range-LP preview to emit a
fixed 5-scenario IL grid: -50%, -20%, 0%, +20%, +50%. Tests pin:
- Exactly 5 scenarios always returned.
- Labels are exact strings in the spec order.
- 0% scenario has ~0 IL.
- ±50% scenarios are more-negative than ±20% scenarios (monotone).
- Tight range (500bps) goes out-of-range at ±50% and ±20%.
- Wide range (2500bps) keeps ±20% in-range.
- Full range (width_bps <= 0) never goes out-of-range.
"""
from __future__ import annotations

import math

import pytest

from src.defi.apr_curve.il_grid import (
    IL_GRID_SCENARIOS,
    ILScenario,
    build_il_grid,
    il_concentrated,
    il_full_range,
)


def test_five_scenarios_always_emitted():
    for width_bps in (0, 100, 500, 1000, 2500, 5000, 10_000):
        grid = build_il_grid(width_bps)
        assert len(grid) == 5, f"width_bps={width_bps} produced {len(grid)} scenarios"


def test_scenario_labels_exact_and_ordered():
    grid = build_il_grid(1000)
    labels = [s.label for s in grid]
    assert labels == ["-50%", "-20%", "0%", "+20%", "+50%"]


def test_zero_scenario_il_is_approximately_zero():
    grid = build_il_grid(1000)
    zero_scenario = next(s for s in grid if s.label == "0%")
    assert abs(zero_scenario.il_pct) < 1e-9
    assert zero_scenario.price_ratio == 1.0
    assert zero_scenario.in_range is True


def test_extreme_more_negative_than_moderate():
    # For a wide range that keeps ±50% in range, ±50% IL must be worse than ±20%.
    grid = build_il_grid(10_000)  # 100% half-width — keeps ±50% in range
    by_label = {s.label: s for s in grid}
    assert by_label["-50%"].il_pct < by_label["-20%"].il_pct
    assert by_label["+50%"].il_pct < by_label["+20%"].il_pct


def test_tight_range_out_of_range_at_extremes():
    # 500bps = 5% half-width. ±20% and ±50% are both far outside.
    grid = build_il_grid(500)
    by_label = {s.label: s for s in grid}
    assert by_label["-50%"].in_range is False
    assert by_label["+50%"].in_range is False
    assert by_label["-20%"].in_range is False
    assert by_label["+20%"].in_range is False
    # 0% always in range.
    assert by_label["0%"].in_range is True


def test_wide_range_keeps_pm20_in_range():
    # 2500bps = 25% half-width. ±20% stays in range, ±50% goes out.
    grid = build_il_grid(2500)
    by_label = {s.label: s for s in grid}
    assert by_label["-20%"].in_range is True
    assert by_label["+20%"].in_range is True
    assert by_label["-50%"].in_range is False
    assert by_label["+50%"].in_range is False


def test_full_range_never_out_of_range():
    for width_bps in (0, -1, -100):
        grid = build_il_grid(width_bps)
        for scenario in grid:
            assert scenario.in_range is True, (
                f"width_bps={width_bps} {scenario.label} unexpectedly out-of-range"
            )


def test_full_range_il_matches_closed_form():
    # IL_full = 2*sqrt(r)/(1+r) - 1
    # At r = 1.5 (+50%): 2*sqrt(1.5)/2.5 - 1 = 0.97979.../1.25 - 1 ≈ -0.02020...
    expected = 2.0 * math.sqrt(1.5) / 2.5 - 1.0
    assert il_full_range(0.5) == pytest.approx(expected)
    # At r = 0.5 (-50%): 2*sqrt(0.5)/1.5 - 1 ≈ -0.0572
    expected_neg = 2.0 * math.sqrt(0.5) / 1.5 - 1.0
    assert il_full_range(-0.5) == pytest.approx(expected_neg)
    # At r = 1.0: IL = 0
    assert il_full_range(0.0) == pytest.approx(0.0)


def test_il_full_range_terminal_loss_on_zero_or_negative_r():
    # r <= 0 → total-loss approximation -1.0
    assert il_full_range(-1.0) == -1.0
    assert il_full_range(-1.5) == -1.0


def test_il_concentrated_full_range_when_width_zero():
    il_zero, in_range = il_concentrated(0.5, 0)
    assert in_range is True
    assert il_zero == pytest.approx(il_full_range(0.5))


def test_il_concentrated_out_of_range_returns_single_asset_il():
    # 500bps = 5% half-width; 50% move is far outside.
    il_oor, in_range = il_concentrated(0.5, 500)
    assert in_range is False
    # Out-of-range IL approximation = -|move|/2 = -0.25
    assert il_oor == pytest.approx(-0.25)


def test_il_concentrated_in_range_is_amplified():
    """Concentrated in-range IL is more negative than full-range IL (CE > 1)."""
    move = 0.05  # 5%
    full = il_full_range(move)
    conc, in_range = il_concentrated(move, 1000)  # 10% half-width
    assert in_range is True
    # Capital efficiency factor 1/0.1 = 10 → conc ~= full * 10
    assert conc < full  # more negative
    assert conc == pytest.approx(full * 10.0)


def test_grid_returns_il_scenario_dataclass():
    grid = build_il_grid(1000)
    for s in grid:
        assert isinstance(s, ILScenario)
        assert isinstance(s.label, str)
        assert isinstance(s.price_ratio, float)
        assert isinstance(s.il_pct, float)
        assert isinstance(s.in_range, bool)


def test_grid_price_ratios_match_scenarios():
    grid = build_il_grid(1000)
    expected_ratios = [1.0 + r for r, _ in IL_GRID_SCENARIOS]
    assert [s.price_ratio for s in grid] == expected_ratios


def test_il_scenario_is_frozen():
    s = ILScenario(label="0%", price_ratio=1.0, il_pct=0.0, in_range=True)
    with pytest.raises(Exception):
        s.label = "changed"  # type: ignore[misc]
