import asyncio

import pytest

from src.platform.event_bus import InMemoryEventBus
from src.platform.stream_hub import StreamHub


@pytest.mark.asyncio
async def test_stream_hub_delivers_published_event_to_subscriber():
    hub = StreamHub()
    queue = await hub.subscribe("analysis.progress")

    await hub.publish(
        "analysis.progress",
        {"event_type": "analysis.progress", "analysis_id": "a-1"},
    )

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received["event_type"] == "analysis.progress"


@pytest.mark.asyncio
async def test_stream_hub_uses_bounded_subscriber_queue():
    hub = StreamHub()
    queue = await hub.subscribe("analysis.progress")

    await hub.publish("analysis.progress", {"event_type": "analysis.progress", "seq": 1})
    await hub.publish("analysis.progress", {"event_type": "analysis.progress", "seq": 2})
    await hub.publish("analysis.progress", {"event_type": "analysis.progress", "seq": 3})

    assert queue.maxsize > 0
    assert queue.qsize() <= queue.maxsize


@pytest.mark.asyncio
async def test_stream_hub_publish_continues_when_subscriber_fails():
    event_bus = InMemoryEventBus()

    async def _failing_subscriber(_: dict) -> None:
        raise RuntimeError("subscriber failed")

    event_bus.subscribe("analysis.progress", _failing_subscriber)
    hub = StreamHub(event_bus=event_bus)
    queue = await hub.subscribe("analysis.progress")

    await hub.publish(
        "analysis.progress",
        {"event_type": "analysis.progress", "analysis_id": "a-1"},
    )

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received["analysis_id"] == "a-1"
