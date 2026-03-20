"""Replay protection for nonce and timestamp validated requests."""

import asyncio
import time
from collections import defaultdict


class ReplayGuard:
    """In-memory nonce replay guard with timestamp skew checks."""

    def __init__(self, ttl_seconds: int = 60, max_skew_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self.max_skew_seconds = max_skew_seconds
        self._seen: dict[str, dict[str, float]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    def now(self) -> float:
        return time.time()

    def _cleanup(self, actor_id: str, current_time: float) -> None:
        actor_nonces = self._seen.get(actor_id, {})
        expired = [nonce for nonce, expires_at in actor_nonces.items() if expires_at <= current_time]
        for nonce in expired:
            del actor_nonces[nonce]
        if not actor_nonces and actor_id in self._seen:
            del self._seen[actor_id]

    async def accept(self, actor_id: str, nonce: str, ts: int) -> bool:
        """Return True when nonce+timestamp is accepted."""
        if not actor_id or not nonce:
            return False

        current_time = self.now()
        if abs(current_time - float(ts)) > self.max_skew_seconds:
            return False

        async with self._lock:
            self._cleanup(actor_id, current_time)
            actor_nonces = self._seen.setdefault(actor_id, {})

            if nonce in actor_nonces:
                return False

            actor_nonces[nonce] = current_time + self.ttl_seconds
            return True
