"""Spec §11 D.7 — explicit >50bps price-drift re-simulation gate."""
from __future__ import annotations

import pytest

from src.defi.freshness import (
    DriftResult,
    assert_drift_within_threshold,
    check_price_drift,
)


def test_no_drift_does_not_breach():
    r = check_price_drift(1000.0, 1000.0)
    assert r.drift_bps == 0.0
    assert r.breached is False
    assert r.must_resimulate is False


def test_small_drift_under_threshold_safe():
    """30 bps drift on a $1000 quote = $3 — under 50 bps threshold."""
    r = check_price_drift(1000.0, 1003.0)
    assert r.drift_bps == pytest.approx(30.0, abs=0.01)
    assert r.breached is False


def test_50bps_exactly_does_not_breach():
    """Threshold is strictly > 50 bps; exact 50 = safe."""
    r = check_price_drift(1000.0, 1005.0)
    assert r.drift_bps == pytest.approx(50.0, abs=0.01)
    assert r.breached is False


def test_just_over_50bps_breaches():
    r = check_price_drift(1000.0, 1006.0)
    assert r.drift_bps == pytest.approx(60.0, abs=0.01)
    assert r.breached is True
    assert r.must_resimulate is True


def test_drift_is_absolute_not_signed():
    """Negative drift (price went down) breaches just like positive."""
    r = check_price_drift(1000.0, 940.0)  # -60 bps absolute
    assert r.drift_bps == pytest.approx(600.0, abs=0.01)
    assert r.breached is True


def test_zero_simulated_quote_forces_resim():
    r = check_price_drift(0.0, 100.0)
    assert r.must_resimulate is True
    assert "No simulated quote" in r.rationale


def test_zero_current_quote_forces_resim():
    r = check_price_drift(100.0, 0.0)
    assert r.must_resimulate is True


def test_custom_threshold_bps():
    """Caller can tighten the threshold for high-stakes flows."""
    r = check_price_drift(1000.0, 1003.0, threshold_bps=20)
    # 30 bps > 20 threshold
    assert r.breached is True


def test_assert_drift_raises_on_breach():
    with pytest.raises(ValueError, match="Price drift"):
        assert_drift_within_threshold(1000.0, 1100.0)


def test_assert_drift_quiet_when_safe():
    # Returns None silently when within threshold.
    assert assert_drift_within_threshold(1000.0, 1001.0) is None


def test_drift_result_to_dict_payload_shape():
    r = check_price_drift(1000.0, 1100.0)
    d = r.to_dict()
    assert set(d.keys()) == {"drift_bps", "threshold_bps", "breached", "must_resimulate", "rationale"}
    assert d["breached"] is True


def test_drift_independent_of_time_freshness():
    """D.7 is value-based; even a 1-second-old quote can drift past 50 bps
    during high volatility. The two gates are AND-ed at broadcast time."""
    # Freshness check would pass at 1s; drift check fails at 200 bps.
    r = check_price_drift(1000.0, 1020.0)
    assert r.drift_bps == pytest.approx(200.0, abs=0.01)
    assert r.breached is True
