import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.api.app import setup_api_routes
from src.api.middleware.cors import cors_middleware
from src.api.middleware.rate_limit import rate_limit_middleware
from src.api.routes.auth import auth_middleware


async def navigate_discover_to_smart_money_to_alerts(client: TestClient) -> None:
    docs_resp = await client.get("/api/v1/docs")
    docs_payload = await docs_resp.json()

    assert docs_resp.status == 200
    workflows = docs_payload.get("core_workflows", {})
    assert "GET /api/v2/defi/discover" in workflows.get("discovery", [])
    assert workflows.get("smart_money") == ["GET /api/v1/smart-money/overview"]
    assert workflows.get("alerts") == ["GET /api/v1/alerts"]

    discover_resp = await client.get("/api/v2/defi/discover")
    assert discover_resp.status == 200

    smart_money_resp = await client.get("/api/v1/smart-money/overview")
    assert smart_money_resp.status == 200

    alerts_resp = await client.get("/api/v1/alerts")
    assert alerts_resp.status == 200


@pytest.mark.asyncio
async def test_discover_to_alert_journey_has_no_dead_ends():
    app = web.Application(middlewares=[cors_middleware, auth_middleware, rate_limit_middleware])
    setup_api_routes(app)

    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        await navigate_discover_to_smart_money_to_alerts(client)
    finally:
        await client.close()
