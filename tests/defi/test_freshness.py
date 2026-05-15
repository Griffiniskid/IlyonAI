"""Tests for spec §11 D.2 30s simulation-freshness gate."""
from __future__ import annotations

import time

import pytest

from src.defi.freshness import (
    FreshnessResult,
    assert_fresh_before_broadcast,
    is_simulation_fresh,
)


def test_fresh_simulation_within_window():
    now = time.time()
    r = is_simulation_fresh(simulated_at=now - 5.0, now=now)
    assert r.is_fresh
    assert not r.must_resimulate
    assert r.elapsed_s == pytest.approx(5.0, abs=0.01)


def test_stale_simulation_past_window():
    now = time.time()
    r = is_simulation_fresh(simulated_at=now - 31.0, now=now)
    assert not r.is_fresh
    assert r.must_resimulate
    assert r.elapsed_s == pytest.approx(31.0, abs=0.01)


def test_boundary_exactly_30s_treated_stale():
    now = time.time()
    r = is_simulation_fresh(simulated_at=now - 30.0, now=now)
    # Threshold is strict less-than → 30.0 exact is stale.
    assert not r.is_fresh


def test_zero_simulated_at_treated_stale():
    r = is_simulation_fresh(simulated_at=0.0)
    assert not r.is_fresh
    assert r.must_resimulate
    assert "No simulation" in r.rationale


def test_custom_threshold_honoured():
    now = time.time()
    r = is_simulation_fresh(simulated_at=now - 45.0, now=now, threshold_s=60)
    assert r.is_fresh
    assert r.threshold_s == 60


def test_assert_fresh_raises_on_stale():
    now = time.time()
    with pytest.raises(ValueError, match="Simulation stale"):
        assert_fresh_before_broadcast(simulated_at=now - 60.0, now=now)


def test_assert_fresh_silent_on_fresh():
    now = time.time()
    # No raise.
    assert_fresh_before_broadcast(simulated_at=now - 5.0, now=now)


def test_result_serialisable_to_dict():
    now = time.time()
    r = is_simulation_fresh(simulated_at=now - 5.0, now=now)
    d = r.to_dict()
    assert d["is_fresh"] is True
    assert d["threshold_s"] == 30
    assert isinstance(d["elapsed_s"], float)
    assert "rationale" in d


def test_negative_elapsed_clamped_to_zero():
    # simulated_at in the future — defensive: don't go negative.
    now = time.time()
    r = is_simulation_fresh(simulated_at=now + 10.0, now=now)
    assert r.elapsed_s == 0.0
    assert r.is_fresh
