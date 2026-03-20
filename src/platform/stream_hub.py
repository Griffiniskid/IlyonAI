import asyncio
from typing import Callable

from src.platform.event_bus import InMemoryEventBus


DEFAULT_SUBSCRIBER_QUEUE_SIZE = 100


class StreamHub:
    def __init__(self, event_bus: InMemoryEventBus | None = None, queue_maxsize: int = DEFAULT_SUBSCRIBER_QUEUE_SIZE) -> None:
        self._event_bus = event_bus or InMemoryEventBus()
        self._queue_maxsize = queue_maxsize
        self._unsubscribers: dict[asyncio.Queue[dict], Callable[[], None]] = {}

    async def subscribe(self, topic: str) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._queue_maxsize)

        async def _subscriber(event: dict) -> None:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        unsubscribe = self._event_bus.subscribe(topic, _subscriber)
        self._unsubscribers[queue] = unsubscribe
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        unsubscribe = self._unsubscribers.pop(queue, None)
        if unsubscribe:
            unsubscribe()

    async def publish(self, topic: str, event: dict) -> None:
        await self._event_bus.publish(topic, event)

    @property
    def dead_letter_queue(self):
        return self._event_bus.dead_letter_queue

    @property
    def circuit_breakers(self):
        return self._event_bus.circuit_breakers


_stream_hub = StreamHub()


def get_stream_hub() -> StreamHub:
    return _stream_hub


def reset_stream_hub_for_test() -> None:
    global _stream_hub
    _stream_hub = StreamHub()


async def publish_test_event(topic: str, event: dict) -> None:
    await _stream_hub.publish(topic, event)
