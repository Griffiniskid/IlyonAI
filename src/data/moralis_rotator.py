"""Moralis API key rotator with rate-limit-aware fallback.

Holds a pool of Moralis API keys. On every request the rotator hands out the
next eligible key. When a request returns HTTP 429 (rate limited) or 401
(invalid), the caller reports it via :meth:`mark_rate_limited` /
:meth:`mark_invalid` and the rotator quarantines that key for `cooldown_s`
seconds before letting it back into the pool.

Env layout:
    MORALIS_API_KEYS=key1,key2,key3       (preferred — comma separated)
    MORALIS_API_KEY=<single key>          (legacy fallback)

The pool rebuilds itself when the env changes, so deployments only need to
update the .env file and restart the worker.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class _KeyState:
    key: str
    cooldown_until: float = 0.0
    consecutive_429s: int = 0
    invalid: bool = False
    used_count: int = 0
    last_used_at: float = field(default_factory=time.time)


class MoralisKeyRotator:
    """Thread-safe rotating pool of Moralis API keys."""

    def __init__(self, keys: Iterable[str] | None = None, *, cooldown_s: float = 60.0):
        seen: set[str] = set()
        normalized: list[str] = []
        for raw in keys or []:
            value = (raw or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        self._states: list[_KeyState] = [_KeyState(key=k) for k in normalized]
        self._cooldown_s = float(cooldown_s)
        self._cursor = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, *, cooldown_s: float = 60.0) -> "MoralisKeyRotator":
        raw = os.environ.get("MORALIS_API_KEYS") or os.environ.get("MORALIS_API_KEY") or ""
        keys = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
        return cls(keys, cooldown_s=cooldown_s)

    @property
    def empty(self) -> bool:
        return not self._states

    @property
    def size(self) -> int:
        return len(self._states)

    def snapshot(self) -> list[dict]:
        now = time.time()
        with self._lock:
            return [
                {
                    "key_tail": state.key[-6:] if state.key else "",
                    "cooldown_remaining_s": max(0.0, state.cooldown_until - now),
                    "consecutive_429s": state.consecutive_429s,
                    "invalid": state.invalid,
                    "used_count": state.used_count,
                }
                for state in self._states
            ]

    def acquire(self) -> str | None:
        """Return the next eligible API key (or None if pool is empty/all
        keys are quarantined). On a fully-quarantined pool we still return
        the least-recently-quarantined key as a best-effort retry rather
        than failing closed.
        """
        if not self._states:
            return None
        now = time.time()
        with self._lock:
            n = len(self._states)
            for _ in range(n):
                state = self._states[self._cursor % n]
                self._cursor = (self._cursor + 1) % n
                if state.invalid:
                    continue
                if state.cooldown_until <= now:
                    state.used_count += 1
                    state.last_used_at = now
                    return state.key
            # All keys are in cooldown: pick the one with the soonest expiry.
            state = min(
                (s for s in self._states if not s.invalid),
                key=lambda s: s.cooldown_until,
                default=None,
            )
            if state is None:
                return None
            state.used_count += 1
            state.last_used_at = now
            return state.key

    def mark_rate_limited(self, key: str, *, cooldown_s: float | None = None) -> None:
        if not key:
            return
        cooldown = float(cooldown_s) if cooldown_s is not None else self._cooldown_s
        with self._lock:
            for state in self._states:
                if state.key == key:
                    state.consecutive_429s += 1
                    # exponential back-off: 60s, 120s, 240s capped at 600s
                    factor = min(2 ** (state.consecutive_429s - 1), 10)
                    state.cooldown_until = time.time() + cooldown * factor
                    return

    def mark_invalid(self, key: str) -> None:
        if not key:
            return
        with self._lock:
            for state in self._states:
                if state.key == key:
                    state.invalid = True
                    return

    def mark_success(self, key: str) -> None:
        if not key:
            return
        with self._lock:
            for state in self._states:
                if state.key == key:
                    state.consecutive_429s = 0
                    return


# Module-level singleton. Tests can call rebuild_rotator() to re-read env.
_rotator: MoralisKeyRotator | None = None
_rotator_lock = threading.Lock()


def get_rotator() -> MoralisKeyRotator:
    global _rotator
    with _rotator_lock:
        if _rotator is None:
            _rotator = MoralisKeyRotator.from_env()
        return _rotator


def rebuild_rotator(keys: Iterable[str] | None = None, *, cooldown_s: float = 60.0) -> MoralisKeyRotator:
    """Rebuild the singleton — useful for tests and runtime config reloads."""
    global _rotator
    with _rotator_lock:
        if keys is None:
            _rotator = MoralisKeyRotator.from_env(cooldown_s=cooldown_s)
        else:
            _rotator = MoralisKeyRotator(keys, cooldown_s=cooldown_s)
        return _rotator
