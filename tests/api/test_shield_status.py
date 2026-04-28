import pytest
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.shield import setup_shield_routes


@pytest.mark.asyncio
async def test_shield_status_shows_chain_availability():
    """Shield status endpoint should report which chains have API keys configured."""
    mock_settings = type("S", (), {
        "etherscan_api_key": "real-key",
        "bscscan_api_key": "",
        "polygonscan_api_key": None,
        "arbiscan_api_key": "real-key",
        "basescan_api_key": None,
        "optimism_etherscan_api_key": None,
        "snowtrace_api_key": None,
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
            chains = body["data"]["chains"]
            assert chains["ethereum"]["available"] is True
            assert chains["bsc"]["available"] is False
            assert chains["arbitrum"]["available"] is True
            assert chains["polygon"]["available"] is False
        finally:
            await client.close()
            await server.close()
