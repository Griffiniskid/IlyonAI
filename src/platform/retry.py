from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")


def run_with_retry(
    fn: Callable[[], T],
    max_attempts: int,
    *,
    base_delay_seconds: float = 0.0,
    backoff_factor: float = 2.0,
    sleep_fn: Callable[[float], None] | None = None,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if base_delay_seconds < 0:
        raise ValueError("base_delay_seconds must be >= 0")
    if backoff_factor < 1:
        raise ValueError("backoff_factor must be >= 1")

    sleeper = sleep_fn or time.sleep

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception:
            if attempt == max_attempts:
                raise
            delay = base_delay_seconds * (backoff_factor ** (attempt - 1))
            if delay > 0:
                sleeper(delay)

    raise RuntimeError("unreachable")


async def run_async_with_retry(
    fn: Callable[[], Awaitable[T]],
    max_attempts: int,
    *,
    base_delay_seconds: float = 0.0,
    backoff_factor: float = 2.0,
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if base_delay_seconds < 0:
        raise ValueError("base_delay_seconds must be >= 0")
    if backoff_factor < 1:
        raise ValueError("backoff_factor must be >= 1")

    sleeper = sleep_fn or asyncio.sleep

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception:
            if attempt == max_attempts:
                raise
            delay = base_delay_seconds * (backoff_factor ** (attempt - 1))
            if delay > 0:
                await sleeper(delay)

    raise RuntimeError("unreachable")
