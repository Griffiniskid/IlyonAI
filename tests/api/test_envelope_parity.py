import json
from datetime import datetime

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request

from src.api.routes import alerts, analysis, chains, contracts, defi, intel, opportunities, portfolio, shield, smart_money, stats, stream, transactions, trending, whale
from tests.helpers import AsyncInMemoryAlertStore


ENVELOPE_KEYS = {"status", "data", "meta", "errors", "trace_id", "freshness"}


def _payload(response: web.Response) -> dict:
    assert response.text is not None
    return json.loads(response.text)


def _assert_envelope(payload: dict) -> None:
    assert set(payload.keys()) == ENVELOPE_KEYS
    assert isinstance(payload["meta"], dict)
    assert isinstance(payload["errors"], list)


@pytest.mark.asyncio
async def test_primary_routes_return_envelope_contract():
    req_analysis = make_mocked_request("GET", "/api/v1/search?query=a")
    req_trending = make_mocked_request("GET", "/api/v1/trending?chain=not-a-chain")
    req_portfolio = make_mocked_request("GET", "/api/v1/portfolio")
    req_transactions = make_mocked_request("GET", "/api/v1/transactions/wallet", match_info={"wallet": "wallet"})
    req_transactions_export_missing_wallet = make_mocked_request(
        "GET",
        "/api/v1/transactions//export",
        match_info={"wallet": ""},
    )
    req_whale = make_mocked_request("GET", "/api/v1/whales?min_amount_usd=bad")
    req_chains = make_mocked_request("GET", "/api/v1/chains")
    req_contracts = make_mocked_request(
        "GET",
        "/api/v1/contract/unknown/0x123",
        match_info={"chain": "unknown", "address": "0x123"},
    )
    req_shield = make_mocked_request("GET", "/api/v1/shield/not-wallet", match_info={"wallet": "not-wallet"})
    req_defi = make_mocked_request("GET", "/api/v1/defi/analyze")
    req_intel = make_mocked_request("GET", "/api/v1/intel/rekt")

    app = web.Application()
    alerts.setup_alert_routes(app, store=AsyncInMemoryAlertStore())
    req_alerts = make_mocked_request("GET", "/api/v1/alerts", app=app)
    req_alert_rule_missing = make_mocked_request(
        "GET",
        "/api/v1/alerts/rules/rule-missing",
        app=app,
        match_info={"rule_id": "rule-missing"},
    )

    req_stream = make_mocked_request("GET", "/api/v1/stream/ws")
    req_opportunities = make_mocked_request("POST", "/opportunities/analyses", app=web.Application())
    req_smart_money = make_mocked_request("GET", "/api/v1/smart-money/overview")

    stats._stats_cache["dashboard_stats"] = {"data": {"ok": True}, "time": datetime.utcnow()}
    req_stats = make_mocked_request("GET", "/api/v1/stats")

    try:
        responses = [
            await analysis.search_tokens(req_analysis),
            await trending.get_trending_tokens(req_trending),
            await portfolio.get_portfolio(req_portfolio),
            await transactions.get_transactions(req_transactions),
            await transactions.export_transactions_csv(req_transactions_export_missing_wallet),
            await whale.get_whale_activity(req_whale),
            await stats.get_dashboard_stats(req_stats),
            await chains.list_chains(req_chains),
            await contracts.get_contract_scan(req_contracts),
            await shield.scan_wallet_approvals(req_shield),
            await defi.analyze_defi(req_defi),
            await intel.list_rekt(req_intel),
            await opportunities.create_opportunity_analysis(req_opportunities),
            await smart_money.get_smart_money_overview(req_smart_money),
            await alerts.list_alerts(req_alerts),
            await alerts.get_alert_rule(req_alert_rule_missing),
            await stream.ws_stream(req_stream),
        ]
    finally:
        stats._stats_cache.clear()

    for response in responses:
        payload = _payload(response)
        _assert_envelope(payload)


@pytest.mark.asyncio
async def test_error_edges_return_envelope_for_invalid_json_and_limit():
    @web.middleware
    async def _auth_context(request: web.Request, handler):
        request["user_wallet"] = "wallet-test"
        request["auth_scopes"] = ["alerts:write"]
        return await handler(request)

    app = web.Application(middlewares=[_auth_context])
    alerts.setup_alert_routes(app, store=AsyncInMemoryAlertStore())
    transactions.setup_transactions_routes(app)

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        create_resp = await client.post(
            "/api/v1/alerts/rules",
            data="{bad",
            headers={"Content-Type": "application/json"},
        )
        assert create_resp.status == 400
        create_payload = await create_resp.json()
        _assert_envelope(create_payload)
        assert create_payload["errors"][0]["code"] == "INVALID_REQUEST"

        update_resp = await client.put(
            "/api/v1/alerts/rules/rule-1",
            data="{bad",
            headers={"Content-Type": "application/json"},
        )
        assert update_resp.status == 400
        update_payload = await update_resp.json()
        _assert_envelope(update_payload)
        assert update_payload["errors"][0]["code"] == "INVALID_REQUEST"

        transactions_resp = await client.get("/api/v1/transactions/wallet?limit=bad")
        assert transactions_resp.status == 400
        transactions_payload = await transactions_resp.json()
        _assert_envelope(transactions_payload)
        assert transactions_payload["errors"][0]["code"] == "INVALID_REQUEST"
    finally:
        await client.close()
        await server.close()
