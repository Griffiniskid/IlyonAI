"""Ordered aggregator fallback chain gated by per-aggregator circuit breakers (V7-035)."""

from __future__ import annotations

from typing import Optional

from src.defi.aggregators.circuit_breaker import RollingCircuitBreaker

# Canonical preference order — first healthy wins.
AGGREGATOR_ORDER: list[str] = ["enso", "1inch", "0x", "kyber", "paraswap"]


class AggregatorFallbackChain:
    """Selects the next healthy aggregator in `order`, gated by `breakers`."""

    def __init__(
        self,
        order: Optional[list[str]] = None,
        breakers: Optional[dict[str, RollingCircuitBreaker]] = None,
    ):
        self.order: list[str] = list(order) if order else list(AGGREGATOR_ORDER)
        if breakers is None:
            self.breakers: dict[str, RollingCircuitBreaker] = {
                a: RollingCircuitBreaker() for a in self.order
            }
        else:
            self.breakers = dict(breakers)
            # Ensure every aggregator in order has a breaker.
            for a in self.order:
                self.breakers.setdefault(a, RollingCircuitBreaker())

    def next_healthy(self) -> Optional[str]:
        """Return first aggregator in order whose breaker is not tripped, else None."""
        for agg in self.order:
            breaker = self.breakers.get(agg)
            if breaker is None or not breaker.is_tripped():
                return agg
        return None

    def record(self, agg: str, success: bool) -> None:
        """Record an attempt outcome for a specific aggregator."""
        if agg in self.breakers:
            self.breakers[agg].record(success)

    def trip(self, agg: str) -> None:
        """Force-trip an aggregator (records enough failures to exceed threshold)."""
        breaker = self.breakers.get(agg)
        if breaker is None:
            return
        for _ in range(breaker.threshold):
            breaker.record(False)

    def reset(self, agg: Optional[str] = None) -> None:
        """Reset a single aggregator's breaker, or all if `agg` is None."""
        if agg is None:
            for b in self.breakers.values():
                b.reset()
        elif agg in self.breakers:
            self.breakers[agg].reset()
