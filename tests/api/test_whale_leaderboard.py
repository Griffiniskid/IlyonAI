from datetime import datetime, timedelta

import pytest
from unittest.mock import AsyncMock, patch
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient

from src.api.routes.whale_leaderboard import (
    aggregate_by_token,
    aggregate_top_wallets,
    compute_composite_scores,
    setup_whale_leaderboard_routes,
)

NOW = datetime(2026, 4, 17, 12, 0, 0)


def _tx(token, wallet, direction, amount, minutes_ago=30, label=None):
    return {
        "signature": f"sig-{token}-{wallet}-{minutes_ago}",
        "wallet_address": wallet,
        "wallet_label": label,
        "token_address": token,
        "token_symbol": token.upper(),
        "token_name": f"Token {token}",
        "direction": direction,
        "amount_usd": amount,
        "tx_timestamp": NOW - timedelta(minutes=minutes_ago),
    }


# ── Pure aggregation tests ──────────────────────────────────────────────────


def test_aggregate_by_token_sums_flows():
    rows = [
        _tx("wif", "w1", "buy", 100_000),
        _tx("wif", "w2", "buy", 200_000),
        _tx("wif", "w1", "sell", 50_000),
        _tx("bonk", "w3", "buy", 500_000),
    ]
    result = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens=set())
    by_token = {r["token_address"]: r for r in result}
    assert by_token["wif"]["gross_buy_usd"] == 300_000
    assert by_token["wif"]["gross_sell_usd"] == 50_000
    assert by_token["wif"]["net_flow_usd"] == 250_000
    assert by_token["wif"]["distinct_buyers"] == 2
    assert by_token["wif"]["distinct_sellers"] == 1
    assert by_token["wif"]["tx_count"] == 3


def test_is_new_on_radar_flag():
    rows = [_tx("wif", "w1", "buy", 100_000)]
    result = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens={"bonk"})
    assert result[0]["is_new_on_radar"] is True
    result2 = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens={"wif"})
    assert result2[0]["is_new_on_radar"] is False


def test_acceleration_ratio():
    # Most recent quarter of a 6h window = last 90 min.
    rows = [
        _tx("wif", "w1", "buy", 100_000, minutes_ago=30),
        _tx("wif", "w2", "buy", 100_000, minutes_ago=60),
        _tx("wif", "w3", "buy", 100_000, minutes_ago=80),
        _tx("wif", "w4", "buy", 100_000, minutes_ago=300),
    ]
    result = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens=set())
    assert result[0]["acceleration"] > 2.0


def test_composite_score_ranks_by_blend():
    rows = [
        _tx("wif", "w1", "buy", 100_000),
        _tx("wif", "w2", "buy", 100_000),
        _tx("wif", "w3", "buy", 100_000),
        _tx("bonk", "w1", "buy", 2_000_000),
    ]
    aggregated = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens=set())
    scored = compute_composite_scores(aggregated)
    by_token = {r["token_address"]: r for r in scored}
    assert by_token["wif"]["composite_score"] > by_token["bonk"]["composite_score"]


def test_aggregate_top_wallets_collapses_across_tokens():
    rows = [
        _tx("wif", "w1", "buy", 100_000, label="Alameda"),
        _tx("bonk", "w1", "buy", 200_000, label="Alameda"),
        _tx("wif", "w2", "sell", 50_000),
    ]
    wallets = aggregate_top_wallets(rows)
    by_addr = {w["address"]: w for w in wallets}
    assert by_addr["w1"]["total_volume_usd"] == 300_000
    assert by_addr["w1"]["tx_count"] == 2
    assert by_addr["w1"]["tokens_touched"] == 2
    assert by_addr["w1"]["label"] == "Alameda"
    assert by_addr["w1"]["dominant_side"] == "buy"


def test_top_wallets_dominant_side_mixed():
    rows = [
        _tx("wif", "w1", "buy", 100_000),
        _tx("wif", "w1", "sell", 100_000),
    ]
    wallets = aggregate_top_wallets(rows)
    assert wallets[0]["dominant_side"] == "mixed"


# ── Route tests ─────────────────────────────────────────────────────────────


def _mock_db_with(rows, prior=None):
    mock = AsyncMock()
    mock.get_whale_aggregations = AsyncMock(return_value={
        "rows": rows, "prior_token_addresses": prior or set(),
    })
    return mock


@pytest.mark.asyncio
async def test_leaderboard_returns_ranked_rows():
    rows = [_tx("wif", "w1", "buy", 100_000), _tx("wif", "w2", "buy", 200_000)]
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=_mock_db_with(rows)):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/leaderboard?window=6h")
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            assert body["data"]["window"] == "6h"
            assert len(body["data"]["rows"]) == 1
            assert body["data"]["rows"][0]["token_address"] == "wif"
            assert "composite_score" in body["data"]["rows"][0]
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_leaderboard_invalid_window_400():
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=_mock_db_with([])):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/leaderboard?window=99h")
            assert resp.status == 400
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_leaderboard_empty_returns_ok_with_empty_rows():
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=_mock_db_with([])):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/leaderboard?window=1h")
            assert resp.status == 200
            body = await resp.json()
            assert body["data"]["rows"] == []
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_top_wallets_returns_rows():
    rows = [_tx("wif", "w1", "buy", 100_000, label="Alameda")]
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=_mock_db_with(rows)):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/top-wallets?window=6h")
            assert resp.status == 200
            body = await resp.json()
            assert body["data"]["rows"][0]["address"] == "w1"
            assert body["data"]["rows"][0]["label"] == "Alameda"
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_leaderboard_db_exception_returns_500_envelope():
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    mock = AsyncMock()
    mock.get_whale_aggregations = AsyncMock(side_effect=Exception("boom"))
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=mock):
        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/leaderboard?window=6h")
            assert resp.status == 500
            body = await resp.json()
            assert body["status"] == "error"
            assert body["errors"][0]["code"] == "LEADERBOARD_FAILED"
        finally:
            await client.close()
            await server.close()
