import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.api.response_envelope import make_envelope
from src.api.response_envelope import ApiResponseMeta
from src.api.routes.smart_money import setup_smart_money_routes


@pytest.mark.asyncio
async def test_smart_money_overview_route_returns_entities():
    app = web.Application()
    setup_smart_money_routes(app)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        resp = await client.get("/api/v1/smart-money/overview")
        payload = await resp.json()

        assert resp.status == 200
        assert isinstance(payload, dict)
        assert payload["status"] == "ok"
        assert payload["errors"] == []
        assert payload["meta"].get("surface") == "smart_money_overview"
        assert payload["trace_id"] is None
        assert payload["freshness"] == "live"
        assert "data" in payload
        assert isinstance(payload["data"], dict)
        assert "entities" in payload["data"]
        assert isinstance(payload["data"]["entities"], list)
        assert "flows" in payload["data"]
        assert isinstance(payload["data"]["flows"], list)
        expected = make_envelope(data={"entities": [], "flows": []})
        assert payload["status"] == expected["status"]
        assert payload["freshness"] == expected["freshness"]
    finally:
        await client.close()


def test_api_response_meta_is_generic_container():
    assert ApiResponseMeta().model_dump(mode="json") == {"data": {}}
