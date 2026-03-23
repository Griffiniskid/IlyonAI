"""Tests for enriched smart money overview endpoint."""

import pytest
from unittest.mock import patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.smart_money import setup_smart_money_routes


FAKE_TRANSACTIONS = [
    {
        "type": "buy",
        "amount_usd": 120000,
        "chain": "solana",
        "wallet_address": "Whale1Addr",
        "wallet_label": "Whale Alpha",
        "token_symbol": "SOL",
        "token_name": "Solana",
        "token_address": "So11111111111111111111111111111111111111112",
        "amount_tokens": 800,
        "dex_name": "Jupiter",
        "signature": "sig_aaa111",
        "timestamp": "2026-03-20T10:00:00Z",
    },
    {
        "type": "buy",
        "amount_usd": 80000,
        "chain": "solana",
        "wallet_address": "Whale1Addr",
        "wallet_label": "Whale Alpha",
        "token_symbol": "JUP",
        "token_name": "Jupiter",
        "token_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        "amount_tokens": 50000,
        "dex_name": "Raydium",
        "signature": "sig_aaa222",
        "timestamp": "2026-03-21T14:00:00Z",
    },
    {
        "type": "sell",
        "amount_usd": 60000,
        "chain": "solana",
        "wallet_address": "Whale2Addr",
        "wallet_label": "Whale Beta",
        "token_symbol": "BONK",
        "token_name": "Bonk",
        "token_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "amount_tokens": 900000000,
        "dex_name": "Orca",
        "signature": "sig_bbb111",
        "timestamp": "2026-03-22T09:30:00Z",
    },
    {
        "type": "sell",
        "amount_usd": 40000,
        "chain": "solana",
        "wallet_address": "Whale3Addr",
        "wallet_label": None,
        "token_symbol": "WIF",
        "token_name": "dogwifhat",
        "token_address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "amount_tokens": 20000,
        "dex_name": "Jupiter",
        "signature": "sig_ccc111",
        "timestamp": "2026-03-22T11:00:00Z",
    },
]


def _make_patched_app():
    """Create a test app with smart money routes and mock SolanaClient."""
    app = web.Application()
    setup_smart_money_routes(app)
    return app


@pytest.mark.asyncio
async def test_enriched_top_buyers_aggregation():
    """Top buyers should be aggregated per wallet with enriched fields."""
    app = _make_patched_app()

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=FAKE_TRANSACTIONS)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            # Whale1Addr has two buy txs: 120k + 80k = 200k aggregated
            assert len(data["top_buyers"]) == 1
            buyer = data["top_buyers"][0]
            assert buyer["wallet_address"] == "Whale1Addr"
            assert buyer["label"] == "Whale Alpha"
            assert buyer["amount_usd"] == 200000
            assert buyer["tx_count"] == 2
            # Largest tx was 120k SOL on Jupiter
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

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=FAKE_TRANSACTIONS)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            # Two sellers: Whale2 (60k) and Whale3 (40k)
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

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=FAKE_TRANSACTIONS)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

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
            assert tx["timestamp"] == "2026-03-20T10:00:00Z"
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

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=FAKE_TRANSACTIONS)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            # inflow = 200k, outflow = 100k -> accumulating
            assert data["flow_direction"] == "accumulating"
            assert data["inflow_usd"] == 200000
            assert data["outflow_usd"] == 100000
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_flow_direction_distributing():
    """Flow direction should be 'distributing' when outflow > inflow."""
    sell_heavy_txs = [
        {"type": "sell", "amount_usd": 90000, "chain": "solana", "wallet_address": "W1",
         "wallet_label": "Seller", "token_symbol": "SOL", "signature": "s1", "timestamp": "2026-03-22T00:00:00Z"},
        {"type": "buy", "amount_usd": 10000, "chain": "solana", "wallet_address": "W2",
         "wallet_label": "Buyer", "token_symbol": "SOL", "signature": "s2", "timestamp": "2026-03-22T01:00:00Z"},
    ]

    app = _make_patched_app()

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=sell_heavy_txs)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

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
    app = _make_patched_app()

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=[])
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

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

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=FAKE_TRANSACTIONS)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            data = body["data"]

            # outflow=100k, total=300k -> 33.33%
            expected = 100000 / 300000 * 100
            assert abs(data["sell_volume_percent"] - expected) < 0.01
        finally:
            await client.close()
            await server.close()
