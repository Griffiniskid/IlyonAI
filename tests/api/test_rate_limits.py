import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.api.middleware import rate_limit as rate_limit_module
from src.api.middleware.rate_limit import RateLimiter, rate_limit_middleware
from src.api.routes.alerts import setup_alert_routes
from src.api.routes.auth import auth_middleware


@pytest.mark.asyncio
async def test_scope_burst_rate_limit_returns_reset_header(monkeypatch):
    class SessionStoreStub:
        async def get_session(self, token):
            assert token == "session-token"
            return {"wallet": "wallet_123456789", "scopes": ["alerts:write"]}

    async def get_session_store_stub():
        return SessionStoreStub()

    monkeypatch.setattr("src.api.routes.auth.get_session_store", get_session_store_stub, raising=False)
    monkeypatch.setattr(rate_limit_module, "_rate_limiter", RateLimiter(requests_per_minute=100, requests_per_hour=100))
    monkeypatch.setattr(
        rate_limit_module,
        "_authenticated_rate_limiter",
        RateLimiter(requests_per_minute=100, requests_per_hour=100),
        raising=False,
    )
    monkeypatch.setattr(rate_limit_module, "_scope_burst_limit_per_minute", 2, raising=False)

    app = web.Application(middlewares=[auth_middleware, rate_limit_middleware])
    setup_alert_routes(app)

    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        statuses = []
        last_response = None
        for _ in range(3):
            last_response = await client.post(
                "/api/v1/alerts/rules",
                headers={
                    "Authorization": "Bearer session-token",
                    "X-Forwarded-For": "127.0.0.1",
                },
                json={"name": "burst", "severity": ["high"]},
            )
            statuses.append(last_response.status)

        assert 429 in statuses
        assert last_response is not None
        assert "X-RateLimit-Reset" in last_response.headers
    finally:
        await client.close()
