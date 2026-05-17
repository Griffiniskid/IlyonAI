"""Aggregator routing primitives: circuit breakers + fallback chain (V7-035)."""

from src.defi.aggregators.circuit_breaker import RollingCircuitBreaker
from src.defi.aggregators.fallback_chain import (
    AGGREGATOR_ORDER,
    AggregatorFallbackChain,
)

__all__ = [
    "RollingCircuitBreaker",
    "AggregatorFallbackChain",
    "AGGREGATOR_ORDER",
]
