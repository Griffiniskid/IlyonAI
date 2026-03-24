"""Tests for enriched smart money overview endpoint (DB-backed)."""

import pytest
from unittest.mock import patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.smart_money import setup_smart_money_routes


# Simulated DB overview results (already direction-mapped: "inflow"/"outflow")
FAKE_DB_OVERVIEW = {
    "transactions": [
        {
            "signature": "sig_aaa111",
            "wallet_address": "Whale1Addr",
            "wallet_label": "Whale Alpha",
            "direction": "inflow",
            "amount_usd": 120000,
            "amount_tokens": 800,
            "token_address": "So11111111111111111111111111111111111111112",
            "token_symbol": "SOL",
            "token_name": "Solana",
            "dex_name": "Jupiter",
            "timestamp": "2026-03-20T10:00:00",
            "chain": "solana",
            "price_usd": 150.0,
        },
        {
            "signature": "sig_aaa222",
            "wallet_address": "Whale1Addr",
            "wallet_label": "Whale Alpha",
            "direction": "inflow",
            "amount_usd": 80000,
            "amount_tokens": 50000,
            "token_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            "token_symbol": "JUP",
            "token_name": "Jupiter",
            "dex_name": "Raydium",
            "timestamp": "2026-03-21T14:00:00",
            "chain": "solana",
            "price_usd": 1.6,
        },
        {
            "signature": "sig_bbb111",
            "wallet_address": "Whale2Addr",
            "wallet_label": "Whale Beta",
            "direction": "outflow",
            "amount_usd": 60000,
            "amount_tokens": 900000000,
            "token_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "token_symbol": "BONK",
            "token_name": "Bonk",
            "dex_name": "Orca",
            "timestamp": "2026-03-22T09:30:00",
            "chain": "solana",
            "price_usd": 0.0001,
        },
        {
            "signature": "sig_ccc111",
            "wallet_address": "Whale3Addr",
            "wallet_label": None,
            "direction": "outflow",
            "amount_usd": 40000,
            "amount_tokens": 20000,
            "token_address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            "token_symbol": "WIF",
            "token_name": "dogwifhat",
            "dex_name": "Jupiter",
            "timestamp": "2026-03-22T11:00:00",
            "chain": "solana",
            "price_usd": 2.0,
        },
    ],
    "inflow_usd": 200000,
    "outflow_usd": 100000,
}


def _make_mock_db(overview=None):
    mock_db = AsyncMock()
    mock_db.get_whale_overview = AsyncMock(return_value=overview or FAKE_DB_OVERVIEW)
    return mock_db


def _make_patched_app():
    app = web.Application()
    setup_smart_money_routes(app)
    return app


@pytest.mark.asyncio
async def test_enriched_top_buyers_aggregation():
    """Top buyers should be aggregated per wallet with enriched fields."""
    app = _make_patched_app()

    with patch("src.api.routes.smart_money.get_database", return_value=_make_mock_db()):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            assert len(data["top_buyers"]) == 1
            buyer = data["top_buyers"][0]
            assert buyer["wallet_address"] == "Whale1Addr"
            assert buyer["label"] == "Whale Alpha"
            assert buyer["amount_usd"] == 200000
            assert buyer["tx_count"] == 2
            assert buyer["token_symbol"] == "SOL"
            assert buyer["dex_name"] == "Jupiter"
            assert "last_seen" in buyer
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_enriched_top_sellers():
    """Top sellers should include enriched fields per wallet."""
    app = _make_patched_app()

    with patch("src.api.routes.smart_money.get_database", return_value=_make_mock_db()):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            assert len(data["top_sellers"]) == 2
            seller1 = data["top_sellers"][0]
            assert seller1["wallet_address"] == "Whale2Addr"
            assert seller1["amount_usd"] == 60000
            assert seller1["token_symbol"] == "BONK"
            assert seller1["dex_name"] == "Orca"
            assert seller1["tx_count"] == 1

            seller2 = data["top_sellers"][1]
            assert seller2["wallet_address"] == "Whale3Addr"
            assert seller2["amount_usd"] == 40000
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_recent_transactions_full_context():
    """Recent transactions should carry all per-tx fields."""
    app = _make_patched_app()

    with patch("src.api.routes.smart_money.get_database", return_value=_make_mock_db()):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            assert len(data["recent_transactions"]) == 4
            tx = data["recent_transactions"][0]
            assert tx["wallet_address"] == "Whale1Addr"
            assert tx["token_symbol"] == "SOL"
            assert tx["signature"] == "sig_aaa111"
            assert tx["direction"] == "inflow"
            assert tx["dex_name"] == "Jupiter"
            assert tx["chain"] == "solana"
            assert tx["amount_usd"] == 120000
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_flow_direction_accumulating():
    """Flow direction should be 'accumulating' when inflow > outflow."""
    app = _make_patched_app()

    with patch("src.api.routes.smart_money.get_database", return_value=_make_mock_db()):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            assert data["flow_direction"] == "accumulating"
            assert data["inflow_usd"] == 200000
            assert data["outflow_usd"] == 100000
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_flow_direction_distributing():
    """Flow direction should be 'distributing' when outflow > inflow."""
    sell_heavy_overview = {
        "transactions": [
            {"signature": "s1", "wallet_address": "W1", "wallet_label": "Seller",
             "direction": "outflow", "amount_usd": 90000, "token_symbol": "SOL",
             "dex_name": "Jupiter", "timestamp": "2026-03-22T00:00:00", "chain": "solana"},
            {"signature": "s2", "wallet_address": "W2", "wallet_label": "Buyer",
             "direction": "inflow", "amount_usd": 10000, "token_symbol": "SOL",
             "dex_name": "Raydium", "timestamp": "2026-03-22T01:00:00", "chain": "solana"},
        ],
        "inflow_usd": 10000,
        "outflow_usd": 90000,
    }

    app = _make_patched_app()

    with patch("src.api.routes.smart_money.get_database", return_value=_make_mock_db(sell_heavy_overview)):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            assert data["flow_direction"] == "distributing"
            assert data["sell_volume_percent"] == 90.0
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_flow_direction_neutral_on_empty():
    """Flow direction should be 'neutral' when there are no transactions."""
    empty_overview = {"transactions": [], "inflow_usd": 0, "outflow_usd": 0}

    app = _make_patched_app()

    with patch("src.api.routes.smart_money.get_database", return_value=_make_mock_db(empty_overview)):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            assert data["flow_direction"] == "neutral"
            assert data["sell_volume_percent"] == 0
            assert data["recent_transactions"] == []
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_sell_volume_percent():
    """Sell volume percent should be outflow / total * 100."""
    app = _make_patched_app()

    with patch("src.api.routes.smart_money.get_database", return_value=_make_mock_db()):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            expected = 100000 / 300000 * 100
            assert abs(data["sell_volume_percent"] - expected) < 0.01
        finally:
            await client.close()
            await server.close()
