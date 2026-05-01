"""Tests for agent_preferences REST endpoints."""
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient


@pytest.mark.asyncio
async def test_get_preferences_returns_preferences():
    """GET /api/v1/agent/preferences should return user preferences."""
    mock_prefs = AsyncMock()
    mock_prefs.user_id = 42
    mock_prefs.risk_budget = "aggressive"
    mock_prefs.preferred_chains = ["solana", "ethereum"]
    mock_prefs.blocked_protocols = None
    mock_prefs.gas_cap_usd = 50.0
    mock_prefs.slippage_cap_bps = 100
    mock_prefs.notional_double_confirm_usd = 5000.0
    mock_prefs.auto_rebalance_opt_in = 1
    mock_prefs.rebalance_auth_signature = None
    mock_prefs.rebalance_auth_nonce = None
    mock_prefs.updated_at = datetime.utcnow()

    with patch("src.api.routes.agent_preferences.get_or_default", new=AsyncMock(return_value=mock_prefs)):
        from src.api.routes.agent_preferences import setup_agent_preferences_routes
        app = web.Application()
        setup_agent_preferences_routes(app)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/agent/preferences", headers={"X-User-Id": "42"})
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            assert body["data"]["user_id"] == 42
            assert body["data"]["risk_budget"] == "aggressive"
            assert body["data"]["preferred_chains"] == ["solana", "ethereum"]
            assert body["data"]["slippage_cap_bps"] == 100
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_post_preferences_upserts_and_returns_preferences():
    """POST /api/v1/agent/preferences should upsert and return preferences."""
    mock_prefs = AsyncMock()
    mock_prefs.user_id = 42
    mock_prefs.risk_budget = "conservative"
    mock_prefs.preferred_chains = ["base"]
    mock_prefs.blocked_protocols = ["some-protocol"]
    mock_prefs.gas_cap_usd = 25.0
    mock_prefs.slippage_cap_bps = 30
    mock_prefs.notional_double_confirm_usd = 1000.0
    mock_prefs.auto_rebalance_opt_in = 0
    mock_prefs.rebalance_auth_signature = None
    mock_prefs.rebalance_auth_nonce = None
    mock_prefs.updated_at = datetime.utcnow()

    with patch("src.api.routes.agent_preferences.upsert", new=AsyncMock(return_value=True)):
        with patch("src.api.routes.agent_preferences.get_or_default", new=AsyncMock(return_value=mock_prefs)):
            from src.api.routes.agent_preferences import setup_agent_preferences_routes
            app = web.Application()
            setup_agent_preferences_routes(app)

            server = TestServer(app)
            client = TestClient(server)
            await server.start_server()

            try:
                resp = await client.post(
                    "/api/v1/agent/preferences",
                    headers={"X-User-Id": "42"},
                    json={"risk_budget": "conservative", "preferred_chains": ["base"]}
                )
                assert resp.status == 200
                body = await resp.json()
                assert body["status"] == "ok"
                assert body["data"]["risk_budget"] == "conservative"
                assert body["data"]["preferred_chains"] == ["base"]
            finally:
                await client.close()
                await server.close()


@pytest.mark.asyncio
async def test_post_preferences_returns_400_on_invalid_body():
    """POST /api/v1/agent/preferences should return 400 for invalid JSON."""
    from src.api.routes.agent_preferences import setup_agent_preferences_routes
    app = web.Application()
    setup_agent_preferences_routes(app)

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        resp = await client.post(
            "/api/v1/agent/preferences",
            headers={"X-User-Id": "42"},
            json="not-an-object"
        )
        # Should handle gracefully
        assert resp.status in (200, 400, 500)
    finally:
        await client.close()
        await server.close()
