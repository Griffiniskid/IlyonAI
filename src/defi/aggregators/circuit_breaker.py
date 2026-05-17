"""Rolling N-of-M circuit breaker for aggregator health tracking (V7-035).

Default policy: 3 failures within the last 5 attempts trips the breaker.
"""

from collections import deque


class RollingCircuitBreaker:
    """Trip when `threshold` failures occur within the last `window` attempts."""

    def __init__(self, window: int = 5, threshold: int = 3):
        if window <= 0:
            raise ValueError("window must be positive")
        if threshold <= 0:
            raise ValueError("threshold must be positive")
        if threshold > window:
            raise ValueError("threshold cannot exceed window")
        self.window = window
        self.threshold = threshold
        self._results: deque[bool] = deque(maxlen=window)

    def record(self, success: bool) -> None:
        """Record a single attempt outcome (True = success, False = failure)."""
        self._results.append(bool(success))

    def is_tripped(self) -> bool:
        """True iff failures within the rolling window meet/exceed threshold."""
        failures = sum(1 for ok in self._results if not ok)
        return failures >= self.threshold

    def reset(self) -> None:
        """Clear the rolling window — breaker becomes healthy."""
        self._results.clear()
