import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar


T = TypeVar("T")


class CoalescedAnalysisRunner:
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Task[T]] = {}

    async def run(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(factory())
            self._inflight[key] = task
        try:
            return await task
        finally:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)
