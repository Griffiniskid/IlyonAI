import pytest
from unittest.mock import patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.smart_money import setup_smart_money_routes


def _make_mock_db(overview):
    mock_db = AsyncMock()
    mock_db.get_whale_overview = AsyncMock(return_value=overview)
    return mock_db


@pytest.mark.asyncio
async def test_smart_money_overview_returns_data():
    """Overview should return flow data when database has transactions."""
    overview = {
        "transactions": [
            {"signature": "s1", "wallet_address": "Abc123", "wallet_label": "Whale A",
             "direction": "inflow", "amount_usd": 50000, "token_symbol": "SOL",
             "dex_name": "Jupiter", "timestamp": "2026-03-22T00:00:00", "chain": "solana"},
            {"signature": "s2", "wallet_address": "Def456", "wallet_label": None,
             "direction": "outflow", "amount_usd": 30000, "token_symbol": "USDC",
             "dex_name": "Raydium", "timestamp": "2026-03-22T01:00:00", "chain": "solana"},
        ],
        "inflow_usd": 50000,
        "outflow_usd": 30000,
    }

    app = web.Application()
    setup_smart_money_routes(app)

    with patch("src.api.routes.smart_money.get_database", return_value=_make_mock_db(overview)):
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
    """Overview should return error envelope when database fails."""
    app = web.Application()
    setup_smart_money_routes(app)

    mock_db = AsyncMock()
    mock_db.get_whale_overview = AsyncMock(side_effect=Exception("DB unavailable"))

    with patch("src.api.routes.smart_money.get_database", return_value=mock_db):
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
