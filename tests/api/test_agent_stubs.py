"""
Tests for feature-flagged stub routes (agent, tokens_bar, auth stubs).
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


@pytest.mark.asyncio
async def test_agent_route_returns_503_when_flag_off():
    from src.api.routes.agent import setup_agent_routes

    app = web.Application()
    setup_agent_routes(app)

    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/v1/agent", json={"session_id": "x", "message": "hi"})
        assert r.status == 503
        body = await r.json()
        assert body["error"] == "agent_v2_disabled"


@pytest.mark.asyncio
async def test_agent_sessions_returns_503_when_flag_off():
    from src.api.routes.agent import setup_agent_routes

    app = web.Application()
    setup_agent_routes(app)

    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/v1/agent/sessions")
        assert r.status == 503


@pytest.mark.asyncio
async def test_agent_session_detail_returns_503_when_flag_off():
    from src.api.routes.agent import setup_agent_routes

    app = web.Application()
    setup_agent_routes(app)

    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/v1/agent/sessions/abc123")
        assert r.status == 503


@pytest.mark.asyncio
async def test_agent_post_message_returns_503_when_flag_off():
    from src.api.routes.agent import setup_agent_routes

    app = web.Application()
    setup_agent_routes(app)

    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/v1/agent/sessions/abc123/messages", json={"text": "hi"})
        assert r.status == 503


@pytest.mark.asyncio
async def test_tokens_bar_returns_503_when_flag_off():
    from src.api.routes.tokens_bar import setup_tokens_bar_routes

    app = web.Application()
    setup_tokens_bar_routes(app)

    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/v1/tokens/ticker")
        assert r.status == 503
        body = await r.json()
        assert body["error"] == "tokens_bar_disabled"


@pytest.mark.asyncio
async def test_auth_stubs_return_501():
    from src.api.routes.auth import setup_auth_routes

    app = web.Application()
    setup_auth_routes(app)

    async with TestClient(TestServer(app)) as client:
        for path in [
            "/api/v1/auth/verify-evm",
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/link-wallet",
        ]:
            r = await client.post(path, json={})
            assert r.status == 501, f"{path} returned {r.status}"
            body = await r.json()
            assert body["error"] == "not_implemented", f"{path} body: {body}"
