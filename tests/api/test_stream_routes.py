import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.api.routes.stream import setup_stream_routes
from src.platform.stream_hub import get_stream_hub, publish_test_event, reset_stream_hub_for_test


@pytest.mark.asyncio
async def test_ws_client_receives_published_event():
    app = web.Application()
    setup_stream_routes(app)

    client = TestClient(TestServer(app))
    await client.start_server()

    ws = await client.ws_connect("/api/v1/stream/ws?topic=analysis.progress")
    await publish_test_event(
        "analysis.progress",
        {"event_type": "analysis.progress", "analysis_id": "a-1"},
    )
    received = await ws.receive_json(timeout=1.0)

    assert received["event_type"] == "analysis.progress"

    await ws.close()
    await client.close()
    reset_stream_hub_for_test()


@pytest.mark.asyncio
async def test_ws_subscription_is_cleaned_up_after_idle_disconnect(monkeypatch):
    monkeypatch.setattr("src.api.routes.stream.HEARTBEAT_SECONDS", 0.05)

    app = web.Application()
    setup_stream_routes(app)

    client = TestClient(TestServer(app))
    await client.start_server()

    ws = await client.ws_connect("/api/v1/stream/ws?topic=analysis.progress")
    await ws.close()

    await asyncio.sleep(0.15)

    hub = get_stream_hub()
    assert "analysis.progress" not in hub._event_bus.subscribers

    await client.close()
    reset_stream_hub_for_test()
