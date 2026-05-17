"""Pin tests for V7-035: rolling 3-of-5 circuit breaker + aggregator fallback chain."""

from __future__ import annotations

import pytest

from src.defi.aggregators.circuit_breaker import RollingCircuitBreaker
from src.defi.aggregators.fallback_chain import (
    AGGREGATOR_ORDER,
    AggregatorFallbackChain,
)


# ---------------------------------------------------------------------------
# RollingCircuitBreaker
# ---------------------------------------------------------------------------


def test_breaker_three_failures_in_five_trips():
    """3 failures within the 5-window must trip the breaker."""
    b = RollingCircuitBreaker(window=5, threshold=3)
    b.record(False)
    b.record(True)
    b.record(False)
    b.record(True)
    b.record(False)
    assert b.is_tripped() is True


def test_breaker_two_failures_in_five_does_not_trip():
    """2 failures within the 5-window must NOT trip."""
    b = RollingCircuitBreaker(window=5, threshold=3)
    b.record(True)
    b.record(False)
    b.record(True)
    b.record(False)
    b.record(True)
    assert b.is_tripped() is False


def test_breaker_window_rolls_old_failures_off():
    """Failures outside the rolling window must not count."""
    b = RollingCircuitBreaker(window=5, threshold=3)
    # 3 early failures
    for _ in range(3):
        b.record(False)
    assert b.is_tripped() is True
    # Push 5 successes — failures fall out of window.
    for _ in range(5):
        b.record(True)
    assert b.is_tripped() is False


def test_breaker_reset_clears_state():
    b = RollingCircuitBreaker(window=5, threshold=3)
    for _ in range(3):
        b.record(False)
    assert b.is_tripped() is True
    b.reset()
    assert b.is_tripped() is False


def test_breaker_rejects_invalid_config():
    with pytest.raises(ValueError):
        RollingCircuitBreaker(window=0, threshold=3)
    with pytest.raises(ValueError):
        RollingCircuitBreaker(window=5, threshold=0)
    with pytest.raises(ValueError):
        RollingCircuitBreaker(window=3, threshold=5)


# ---------------------------------------------------------------------------
# AggregatorFallbackChain
# ---------------------------------------------------------------------------


def test_default_order_constant():
    assert AGGREGATOR_ORDER == ["enso", "1inch", "0x", "kyber", "paraswap"]


def test_chain_all_healthy_returns_enso():
    chain = AggregatorFallbackChain()
    assert chain.next_healthy() == "enso"


def test_chain_trip_enso_falls_to_1inch():
    chain = AggregatorFallbackChain()
    chain.trip("enso")
    assert chain.next_healthy() == "1inch"


def test_chain_trip_enso_1inch_0x_falls_to_kyber():
    chain = AggregatorFallbackChain()
    chain.trip("enso")
    chain.trip("1inch")
    chain.trip("0x")
    assert chain.next_healthy() == "kyber"


def test_chain_trip_all_returns_none():
    chain = AggregatorFallbackChain()
    for a in AGGREGATOR_ORDER:
        chain.trip(a)
    assert chain.next_healthy() is None


def test_chain_order_respected_under_partial_trip():
    """Even with later aggregators healthy, earlier healthy ones win."""
    chain = AggregatorFallbackChain()
    chain.trip("1inch")  # mid-chain trip
    # enso still healthy, should be picked despite 1inch trip.
    assert chain.next_healthy() == "enso"
    chain.trip("enso")
    # Now 1inch is tripped, enso is tripped → next healthy = "0x".
    assert chain.next_healthy() == "0x"


def test_chain_record_propagates_to_breaker():
    chain = AggregatorFallbackChain()
    # Record 3 failures on enso via record() → should trip per 3-of-5 default.
    chain.record("enso", False)
    chain.record("enso", False)
    chain.record("enso", False)
    assert chain.breakers["enso"].is_tripped() is True
    assert chain.next_healthy() == "1inch"


def test_chain_record_unknown_aggregator_is_noop():
    chain = AggregatorFallbackChain()
    # Must not raise.
    chain.record("nonexistent", False)
    assert chain.next_healthy() == "enso"


def test_chain_reset_all_restores_health():
    chain = AggregatorFallbackChain()
    for a in AGGREGATOR_ORDER:
        chain.trip(a)
    assert chain.next_healthy() is None
    chain.reset()
    assert chain.next_healthy() == "enso"


def test_chain_reset_single_aggregator():
    chain = AggregatorFallbackChain()
    chain.trip("enso")
    assert chain.next_healthy() == "1inch"
    chain.reset("enso")
    assert chain.next_healthy() == "enso"


def test_chain_custom_order_respected():
    custom = ["paraswap", "kyber", "enso"]
    chain = AggregatorFallbackChain(order=custom)
    assert chain.next_healthy() == "paraswap"
    chain.trip("paraswap")
    assert chain.next_healthy() == "kyber"


def test_chain_custom_breakers_used():
    """Caller-supplied breakers must be the ones consulted."""
    custom_breaker = RollingCircuitBreaker(window=2, threshold=1)
    breakers = {a: RollingCircuitBreaker() for a in AGGREGATOR_ORDER}
    breakers["enso"] = custom_breaker
    chain = AggregatorFallbackChain(breakers=breakers)
    # 1 failure trips the custom 1-of-2 breaker.
    chain.record("enso", False)
    assert chain.next_healthy() == "1inch"
