from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class _CacheEntry(Generic[T]):
    expires_at: float
    value: T


class TTLScoreCache(Generic[T]):
    def __init__(self, ttl_seconds: float, clock: Callable[[], float] | None = None) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock or time.time
        self._entries: dict[str, _CacheEntry[T]] = {}

    def get_or_set(self, key: str, factory: Callable[[], T]) -> T:
        now = self._clock()
        entry = self._entries.get(key)
        if entry is not None and entry.expires_at >= now:
            return entry.value
        value = factory()
        self._entries[key] = _CacheEntry(expires_at=now + self._ttl_seconds, value=value)
        return value

    def clear(self) -> None:
        self._entries.clear()
