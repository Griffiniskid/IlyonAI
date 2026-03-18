import asyncio
from collections.abc import Callable
from typing import Any, Coroutine


class CoalescedAnalysisRunner:
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    async def run(self, key: str, factory: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(factory())
            self._inflight[key] = task
            task.add_done_callback(lambda finished_task: self._clear_inflight(key, finished_task))
        return await asyncio.shield(task)

    def _clear_inflight(self, key: str, task: asyncio.Task[Any]) -> None:
        if self._inflight.get(key) is task:
            self._inflight.pop(key, None)
