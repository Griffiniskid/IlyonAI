import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.wallet_intel import setup_wallet_intel_routes


@pytest.mark.asyncio
async def test_profile_returns_wallet_and_label():
    """Profile endpoint should return wallet address, label, and recent_transactions."""
    mock_db_result = {
        "volume_usd": 100000,
        "tx_count": 1,
        "transactions": [
            {
                "wallet_address": "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",
                "amount_usd": 100000,
                "type": "buy",
                "token_symbol": "SOL",
            },
        ],
        "label": None,
    }
    mock_on_chain = {
        "chain_balances": {},
        "active_chains": [],
        "active_chain_count": 0,
        "is_multi_chain": False,
    }

    app = web.Application()
    setup_wallet_intel_routes(app)

    with patch("src.api.routes.wallet_intel._fetch_db_profile", new_callable=AsyncMock, return_value=mock_db_result), \
         patch("src.api.routes.wallet_intel._enrich_solana_wallet", new_callable=AsyncMock, return_value=mock_on_chain):

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get(
                "/api/v1/wallets/5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9/profile"
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            data = body["data"]
            assert data["wallet"] == "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9"
            assert data["label"] == "Alameda"
            assert data["volume_usd"] == 100000
            assert data["transaction_count"] == 1
            assert len(data["recent_transactions"]) == 1
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_profile_unknown_wallet_has_no_label():
    """Profile for an unknown wallet should return null label and still succeed."""
    mock_db_result = {
        "volume_usd": 0,
        "tx_count": 0,
        "transactions": [],
        "label": None,
    }
    mock_on_chain = {
        "chain_balances": {},
        "active_chains": [],
        "active_chain_count": 0,
        "is_multi_chain": False,
    }

    app = web.Application()
    setup_wallet_intel_routes(app)

    with patch("src.api.routes.wallet_intel._fetch_db_profile", new_callable=AsyncMock, return_value=mock_db_result), \
         patch("src.api.routes.wallet_intel._enrich_solana_wallet", new_callable=AsyncMock, return_value=mock_on_chain):

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/wallets/UnknownAddr123/profile")
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            data = body["data"]
            assert data["wallet"] == "UnknownAddr123"
            assert data["label"] is None
            assert data["volume_usd"] == 0.0
            assert data["transaction_count"] == 0
            assert data["recent_transactions"] == []
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_forensics_degraded_when_engine_unavailable():
    """Forensics should return 503 when the engine throws."""
    app = web.Application()
    setup_wallet_intel_routes(app)

    with patch(
        "src.analytics.wallet_forensics.WalletForensicsEngine",
        side_effect=Exception("engine broken"),
    ):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/wallets/SomeWallet/forensics")
            assert resp.status == 503
            body = await resp.json()
            assert body["status"] == "error"
            assert body["errors"][0]["code"] == "FORENSICS_FAILED"
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_forensics_returns_analysis():
    """Forensics should relay engine results when the engine succeeds."""
    mock_result = MagicMock()
    mock_result.risk_level = MagicMock(value="HIGH")
    mock_result.reputation_score = 25.0
    mock_result.tokens_deployed = 5
    mock_result.rugged_tokens = 3
    mock_result.active_tokens = 2
    mock_result.rug_percentage = 60.0
    mock_result.patterns_detected = ["rapid_deployment", "lp_removal_pattern"]
    mock_result.pattern_severity = "HIGH"
    mock_result.funding_risk = 0.8
    mock_result.confidence = 75.0
    mock_result.evidence_summary = "3 of 5 tokens rugged within 48h"

    mock_engine_instance = AsyncMock()
    mock_engine_instance.analyze_wallet = AsyncMock(return_value=mock_result)

    app = web.Application()
    setup_wallet_intel_routes(app)

    with patch(
        "src.analytics.wallet_forensics.WalletForensicsEngine",
        return_value=mock_engine_instance,
    ):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/wallets/SuspiciousAddr/forensics")
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            data = body["data"]
            assert data["risk_level"] == "HIGH"
            assert data["reputation_score"] == 25.0
            assert data["tokens_deployed"] == 5
            assert data["rugged_tokens"] == 3
            assert data["rug_percentage"] == 60.0
            assert data["patterns_detected"] == ["rapid_deployment", "lp_removal_pattern"]
            assert data["pattern_severity"] == "HIGH"
            assert data["funding_risk"] == 0.8
            assert data["confidence"] == 75.0
            assert data["evidence_summary"] == "3 of 5 tokens rugged within 48h"
        finally:
            await client.close()
            await server.close()
