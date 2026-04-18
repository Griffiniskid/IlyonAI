import pytest
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.shield import setup_shield_routes


@pytest.mark.asyncio
async def test_shield_status_shows_chain_availability():
    """Shield status endpoint should report which chains have RPC endpoints configured."""
    mock_settings = type("S", (), {
        "ethereum_rpc_url": "https://eth.llamarpc.com",
        "bsc_rpc_url": "",
        "polygon_rpc_url": None,
        "arbitrum_rpc_url": "https://arb1.arbitrum.io/rpc",
        "base_rpc_url": None,
        "optimism_rpc_url": None,
        "avalanche_rpc_url": None,
    })()

    with patch("src.api.routes.shield.settings", mock_settings):
        app = web.Application()
        # Don't run full setup (no init_shield), just register the status route
        app.router.add_get("/api/v1/shield/status", __import__("src.api.routes.shield", fromlist=["get_shield_status"]).get_shield_status)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/shield/status")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]
            chains = data["chains"]
            assert chains["ethereum"]["available"] is True
            assert chains["ethereum"]["method"] == "rpc_eth_getLogs"
            assert chains["bsc"]["available"] is False
            assert chains["arbitrum"]["available"] is True
            assert chains["polygon"]["available"] is False
            assert data["mode"] == "rpc_direct"
        finally:
            await client.close()
            await server.close()
