import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.alerts import setup_alert_routes, ALERT_STORE_KEY
from src.alerts.models import AlertRecord
from tests.helpers import AsyncInMemoryAlertStore


@pytest.mark.asyncio
async def test_alerts_list_filters_by_severity():
    app = web.Application()
    store = AsyncInMemoryAlertStore()
    setup_alert_routes(app, store=store)

    await store.add_alert(AlertRecord(id="a-1", state="new", severity="high", title="Whale dump"))
    await store.add_alert(AlertRecord(id="a-2", state="new", severity="low", title="Minor blip"))

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        list_resp = await client.get("/api/v1/alerts?severity=high")
        assert list_resp.status == 200
        body = await list_resp.json()
        assert body["status"] == "ok"
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == "a-1"
        assert body["data"][0]["severity"] == "high"
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
async def test_alert_patch_supports_lifecycle_actions_and_snooze():
    app = web.Application()
    store = AsyncInMemoryAlertStore()
    setup_alert_routes(app, store=store)

    await store.add_alert(AlertRecord(id="a-1", state="new", severity="high", title="Whale dump"))

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        seen_resp = await client.patch("/api/v1/alerts/a-1", json={"action": "seen"})
        assert seen_resp.status == 200
        seen_body = await seen_resp.json()
        assert seen_body["data"]["state"] == "seen"

        ack_resp = await client.patch("/api/v1/alerts/a-1", json={"action": "acknowledge"})
        assert ack_resp.status == 200
        ack_body = await ack_resp.json()
        assert ack_body["data"]["state"] == "acknowledged"

        snooze_resp = await client.patch(
            "/api/v1/alerts/a-1",
            json={"action": "snooze", "snoozed_until": "2026-03-21T10:00:00Z"},
        )
        assert snooze_resp.status == 200
        snooze_body = await snooze_resp.json()
        assert snooze_body["data"]["snoozed_until"] == "2026-03-21T10:00:00Z"

        bad_resp = await client.patch("/api/v1/alerts/a-1", json={"action": "bogus"})
        assert bad_resp.status == 400
    finally:
        await client.close()
        await server.close()
