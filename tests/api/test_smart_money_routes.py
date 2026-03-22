import pytest
from unittest.mock import patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.smart_money import setup_smart_money_routes


@pytest.mark.asyncio
async def test_smart_money_overview_returns_data():
    """Overview should return flow data when SolanaClient works."""
    mock_transactions = [
        {"type": "buy", "amount_usd": 50000, "chain": "solana", "wallet_address": "Abc123", "wallet_label": "Whale A"},
        {"type": "sell", "amount_usd": 30000, "chain": "solana", "wallet_address": "Def456", "wallet_label": None},
    ]

    app = web.Application()
    setup_smart_money_routes(app)

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=mock_transactions)
        instance.close = AsyncMock()
        MockClient.return_value = instance
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            data = body["data"]
            assert data["inflow_usd"] == 50000
            assert data["outflow_usd"] == 30000
            assert data["net_flow_usd"] == 20000
            assert len(data["top_buyers"]) == 1
            assert len(data["top_sellers"]) == 1
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_smart_money_overview_error_returns_error_envelope():
    """Overview should return error envelope when SolanaClient fails, not silent zeros."""
    app = web.Application()
    setup_smart_money_routes(app)

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        MockClient.side_effect = Exception("RPC unavailable")

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 502
            body = await resp.json()
            assert body["status"] == "error"
        finally:
            await client.close()
            await server.close()
