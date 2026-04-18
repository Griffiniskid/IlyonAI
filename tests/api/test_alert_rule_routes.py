import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.alerts import setup_alert_routes
from src.api.routes.auth import auth_middleware
from tests.helpers import AsyncInMemoryAlertStore


@pytest.mark.asyncio
async def test_alert_rule_crud_and_severity_filter(monkeypatch):
    class SessionStoreStub:
        async def get_session(self, token):
            assert token == "session-token"
            return {"wallet": "wallet_123456789", "scopes": ["alerts:write"]}

    async def get_session_store_stub():
        return SessionStoreStub()

    monkeypatch.setattr("src.api.routes.auth.get_session_store", get_session_store_stub, raising=False)

    app = web.Application(middlewares=[auth_middleware])
    setup_alert_routes(app, store=AsyncInMemoryAlertStore())
    
    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()
    
    try:
        create_resp = await client.post(
            "/api/v1/alerts/rules",
            headers={"Authorization": "Bearer session-token"},
            json={"name": "high-only", "severity": ["high", "critical"]},
        )
        assert create_resp.status == 201
        created = await create_resp.json()
        rule_id = created["data"]["id"]

        list_rules_resp = await client.get("/api/v1/alerts/rules")
        assert list_rules_resp.status == 200
        listed = await list_rules_resp.json()
        assert any(rule["id"] == rule_id for rule in listed["data"])

        get_resp = await client.get(f"/api/v1/alerts/rules/{rule_id}")
        assert get_resp.status == 200
        fetched = await get_resp.json()
        assert fetched["data"]["name"] == "high-only"

        update_resp = await client.put(
            f"/api/v1/alerts/rules/{rule_id}",
            headers={"Authorization": "Bearer session-token"},
            json={"name": "crit-only", "severity": ["critical"]},
        )
        assert update_resp.status == 200
        updated = await update_resp.json()
        assert updated["data"]["name"] == "crit-only"
        assert updated["data"]["severity"] == ["critical"]

        delete_resp = await client.delete(
            f"/api/v1/alerts/rules/{rule_id}",
            headers={"Authorization": "Bearer session-token"},
        )
        assert delete_resp.status == 204

        missing_resp = await client.get(f"/api/v1/alerts/rules/{rule_id}")
        assert missing_resp.status == 404

        list_resp = await client.get("/api/v1/alerts?severity=high")
        assert list_resp.status == 200
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
async def test_alert_rule_rejects_invalid_payload_with_400(monkeypatch):
    class SessionStoreStub:
        async def get_session(self, token):
            assert token == "session-token"
            return {"wallet": "wallet_123456789", "scopes": ["alerts:write"]}

    async def get_session_store_stub():
        return SessionStoreStub()

    monkeypatch.setattr("src.api.routes.auth.get_session_store", get_session_store_stub, raising=False)

    app = web.Application(middlewares=[auth_middleware])
    setup_alert_routes(app, store=AsyncInMemoryAlertStore())

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        invalid_create = await client.post(
            "/api/v1/alerts/rules",
            headers={"Authorization": "Bearer session-token"},
            json={"name": 123, "severity": "high"},
        )
        assert invalid_create.status == 400

        create_resp = await client.post(
            "/api/v1/alerts/rules",
            headers={"Authorization": "Bearer session-token"},
            json={"name": "ok", "severity": ["high"]},
        )
        body = await create_resp.json()
        rule_id = body["data"]["id"]

        invalid_update = await client.put(
            f"/api/v1/alerts/rules/{rule_id}",
            headers={"Authorization": "Bearer session-token"},
            json={"severity": [1, 2]},
        )
        assert invalid_update.status == 400
    finally:
        await client.close()
        await server.close()
