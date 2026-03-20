import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.alerts import setup_alert_routes, ALERT_STORE_KEY
from src.alerts.models import AlertRecord

@pytest.mark.asyncio
async def test_alerts_list_filters_by_severity():
    app = web.Application()
    setup_alert_routes(app)

    store = app[ALERT_STORE_KEY]
    store.add_alert(AlertRecord(id="a-1", state="new", severity="high", title="Whale dump"))
    store.add_alert(AlertRecord(id="a-2", state="new", severity="low", title="Minor blip"))
    
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
