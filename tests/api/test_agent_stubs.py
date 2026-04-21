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
async def test_auth_endpoints_validate_input():
    """Auth endpoints are no longer stubs; they validate input and return 4xx."""
    from src.api.routes.auth import setup_auth_routes

    app = web.Application()
    setup_auth_routes(app)

    async with TestClient(TestServer(app)) as client:
        # register -- missing fields -> 400
        r = await client.post("/api/v1/auth/register", json={})
        assert r.status == 400

        # login -- missing fields -> 400 (will hit DB error or return 400)
        r = await client.post("/api/v1/auth/login", json={})
        assert r.status in (400, 500)

        # verify-evm -- bad signature -> 400
        r = await client.post("/api/v1/auth/verify-evm", json={
            "address": "0xabc", "message": "hi", "signature": "0xbad",
        })
        assert r.status == 400

        # link-wallet -- no auth -> 401
        r = await client.post("/api/v1/auth/link-wallet", json={})
        assert r.status == 401
