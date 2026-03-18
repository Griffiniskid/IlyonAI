import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from src.api.app import create_api_app
from src.api.middleware import rate_limit as rate_limit_module
from src.api.middleware.rate_limit import RateLimiter, rate_limit_middleware
from src.api.routes.auth import auth_middleware


@pytest.mark.asyncio
async def test_api_app_registers_auth_middleware_before_rate_limit_middleware():
    app = create_api_app()

    assert app.middlewares[1] is auth_middleware
    assert app.middlewares[2] is rate_limit_middleware


@pytest.mark.asyncio
async def test_authenticated_wallet_key_is_available_before_rate_limiting(monkeypatch):
    class SessionStoreStub:
        async def get_session(self, token):
            assert token == "session-token"
            return {"wallet": "wallet_123456789"}

    async def get_session_store_stub():
        return SessionStoreStub()

    monkeypatch.setattr("src.api.routes.auth.get_session_store", get_session_store_stub, raising=False)
    monkeypatch.setattr(rate_limit_module, "_rate_limiter", RateLimiter(requests_per_minute=5, requests_per_hour=5))
    monkeypatch.setattr(rate_limit_module, "_authenticated_rate_limiter", RateLimiter(requests_per_minute=1, requests_per_hour=1), raising=False)

    async def handler(request):
        return web.json_response({"rate_limit_key": request.get("rate_limit_key")})

    request_one = make_mocked_request(
        "GET",
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer session-token", "X-Forwarded-For": "127.0.0.1"},
    )
    response_one = await auth_middleware(request_one, lambda request: rate_limit_middleware(request, handler))

    assert response_one.status == 200
    assert request_one["user_wallet"] == "wallet_123456789"
    assert request_one["rate_limit_key"] == "wallet:wallet_1"

    request_two = make_mocked_request(
        "GET",
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer session-token", "X-Forwarded-For": "127.0.0.1"},
    )
    response_two = await auth_middleware(request_two, lambda request: rate_limit_middleware(request, handler))

    assert response_two.status == 429
