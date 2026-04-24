import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.alerts.audit_log import clear_audit_log, fetch_latest_audit_record
from src.api.routes.alerts import setup_alert_routes
from src.api.routes.auth import auth_middleware


@pytest.mark.asyncio
async def test_alert_rule_change_writes_audit_record_with_actor_and_trace(monkeypatch):
    class SessionStoreStub:
        async def get_session(self, token):
            assert token == "session-token"
            return {"wallet": "wallet_123456789", "scopes": ["alerts:write"]}

    async def get_session_store_stub():
        return SessionStoreStub()

    monkeypatch.setattr("src.api.routes.auth.get_session_store", get_session_store_stub, raising=False)
    clear_audit_log()

    app = web.Application(middlewares=[auth_middleware])
    setup_alert_routes(app)

    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        response = await client.post(
            "/api/v1/alerts/rules",
            headers={
                "Authorization": "Bearer session-token",
                "X-Trace-Id": "trace-123",
            },
            json={"name": "high-only", "severity": ["high"]},
        )
        assert response.status == 201

        audit = await fetch_latest_audit_record("alert_rule.create")
        assert audit is not None
        assert audit["actor_id"] == "wallet_123456789"
        assert audit["trace_id"] == "trace-123"
    finally:
        await client.close()
