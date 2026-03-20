import base64
import hashlib
import hmac

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.api.routes.alerts import setup_alert_routes
from src.api.routes.auth import auth_middleware
from src.api.middleware.replay_guard import ReplayGuard
from src.api.middleware.webhook_signature import verify_webhook_signature


@pytest.mark.asyncio
async def test_alert_rule_mutation_requires_scoped_auth():
    app = web.Application(middlewares=[auth_middleware])
    setup_alert_routes(app)

    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        response = await client.post(
            "/api/v1/alerts/rules",
            json={"name": "high-only", "severity": ["high"]},
        )
        assert response.status == 401
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_alert_rule_mutation_rejects_missing_write_scope(monkeypatch):
    class SessionStoreStub:
        async def get_session(self, token):
            assert token == "session-token"
            return {"wallet": "wallet_123456789", "scopes": ["alerts:read"]}

    async def get_session_store_stub():
        return SessionStoreStub()

    monkeypatch.setattr("src.api.routes.auth.get_session_store", get_session_store_stub, raising=False)

    app = web.Application(middlewares=[auth_middleware])
    setup_alert_routes(app)

    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        response = await client.post(
            "/api/v1/alerts/rules",
            headers={"Authorization": "Bearer session-token"},
            json={"name": "high-only", "severity": ["high"]},
        )
        assert response.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_alert_rule_mutation_rejects_invalid_webhook_signature(monkeypatch):
    class SessionStoreStub:
        async def get_session(self, token):
            assert token == "session-token"
            return {"wallet": "wallet_123456789", "scopes": ["alerts:write"]}

    async def get_session_store_stub():
        return SessionStoreStub()

    monkeypatch.setattr("src.api.routes.auth.get_session_store", get_session_store_stub, raising=False)
    monkeypatch.setattr("src.api.routes.alerts.settings.webhook_signing_secret", "webhook-secret", raising=False)

    app = web.Application(middlewares=[auth_middleware])
    setup_alert_routes(app)

    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        response = await client.post(
            "/api/v1/alerts/rules",
            headers={
                "Authorization": "Bearer session-token",
                "X-Webhook-Signature": "bad-signature",
            },
            json={"name": "high-only", "severity": ["high"]},
        )
        assert response.status == 401
    finally:
        await client.close()


def test_webhook_signature_verification_helper():
    secret = "top-secret"
    payload = "{\"event\":\"alert\"}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    assert verify_webhook_signature(payload, signature, secret) is True
    assert verify_webhook_signature(payload, base64.b64encode(b"bad").decode("utf-8"), secret) is False


@pytest.mark.asyncio
async def test_replay_guard_rejects_duplicate_nonce():
    guard = ReplayGuard(ttl_seconds=60, max_skew_seconds=30)

    first = await guard.accept("user-1", "nonce-1", int(guard.now()))
    second = await guard.accept("user-1", "nonce-1", int(guard.now()))

    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_replay_guard_rejects_stale_timestamp():
    guard = ReplayGuard(ttl_seconds=60, max_skew_seconds=30)
    assert await guard.accept("user-1", "nonce-old", 1) is False
