from __future__ import annotations

import time


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_seconds: int = 30) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_seconds < 1:
            raise ValueError("recovery_seconds must be >= 1")

        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.failures = 0
        self.state = "closed"
        self._opened_at: float | None = None

    def can_execute(self) -> bool:
        if self.state != "open":
            return True
        if self._opened_at is None:
            return False
        if (time.time() - self._opened_at) >= self.recovery_seconds:
            self.state = "half_open"
            return True
        return False

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "open"
            self._opened_at = time.time()

    def record_success(self) -> None:
        self.failures = 0
        self.state = "closed"
        self._opened_at = None
