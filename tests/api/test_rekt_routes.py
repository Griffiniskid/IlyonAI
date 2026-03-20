import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.api.routes.intel import cleanup_intel, init_intel, setup_intel_routes


@pytest.mark.asyncio
async def test_rekt_list_returns_envelope_cursor_and_freshness():
    app = web.Application()
    setup_intel_routes(app)
    await init_intel(app)

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/v1/intel/rekt?limit=10")
        assert response.status == 200
        payload = await response.json()

    await cleanup_intel(app)

    assert "data" in payload
    assert "incidents" in payload["data"]
    assert "meta" in payload
    assert "cursor" in payload["meta"]
    assert "freshness" in payload["meta"]


@pytest.mark.asyncio
async def test_rekt_detail_returns_envelope_shape():
    app = web.Application()
    setup_intel_routes(app)
    await init_intel(app)

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/v1/intel/rekt/ronin-2022")
        assert response.status == 200
        payload = await response.json()

    await cleanup_intel(app)

    assert "data" in payload
    assert payload["data"]["id"] == "ronin-2022"
    assert "meta" in payload
    assert payload["meta"].get("freshness") == "warm"


@pytest.mark.asyncio
async def test_rekt_list_rejects_negative_limit_and_min_amount():
    app = web.Application()
    setup_intel_routes(app)
    await init_intel(app)

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/v1/intel/rekt?limit=-1&min_amount=-10")
        assert response.status == 400
        payload = await response.json()

    await cleanup_intel(app)

    assert payload["status"] == "error"
    assert payload["errors"][0]["code"] == "INVALID_QUERY"
