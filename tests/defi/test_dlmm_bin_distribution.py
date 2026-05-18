"""V7 §1 — pin tests for DLMM bin distribution shapes."""
from __future__ import annotations

import math

from src.defi.dlmm import (
    spot_distribution,
    curve_distribution,
    bid_ask_distribution,
)


def test_spot_uniform():
    dist = spot_distribution(active_bin=100, range_bins=2)
    assert len(dist) == 5
    weights = list(dist.values())
    assert all(math.isclose(w, weights[0]) for w in weights)
    assert math.isclose(sum(dist.values()), 1.0, rel_tol=1e-9)


def test_curve_peaks_at_active():
    dist = curve_distribution(active_bin=100, range_bins=3)
    assert max(dist, key=dist.get) == 100
    assert math.isclose(sum(dist.values()), 1.0, rel_tol=1e-9)


def test_curve_symmetric():
    dist = curve_distribution(active_bin=50, range_bins=2)
    assert math.isclose(dist[48], dist[52], rel_tol=1e-9)
    assert math.isclose(dist[49], dist[51], rel_tol=1e-9)


def test_bid_ask_minimum_at_active():
    dist = bid_ask_distribution(active_bin=100, range_bins=3)
    assert dist[100] <= dist[97]
    assert dist[100] <= dist[103]
    assert math.isclose(sum(dist.values()), 1.0, rel_tol=1e-6)


def test_bid_ask_symmetric():
    dist = bid_ask_distribution(active_bin=10, range_bins=2)
    assert math.isclose(dist[8], dist[12], rel_tol=1e-9)


def test_zero_range_returns_single_bin():
    spot = spot_distribution(active_bin=50, range_bins=0)
    curve = curve_distribution(active_bin=50, range_bins=0)
    ba = bid_ask_distribution(active_bin=50, range_bins=0)
    assert list(spot.keys()) == [50] and math.isclose(spot[50], 1.0)
    assert list(curve.keys()) == [50] and math.isclose(curve[50], 1.0)
    assert list(ba.keys()) == [50] and math.isclose(ba[50], 1.0)
