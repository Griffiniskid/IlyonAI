import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from typing import Any, cast

from src.defi.intelligence_engine import DefiIntelligenceEngine


class FakeOpportunityService:
    def __init__(self):
        self.compare_calls = []

    async def compare_opportunities(self, items):
        self.compare_calls.append(items)
        return {"items": items, "matrix": []}


class FakeEngine:
    def __init__(self):
        self.compare_calls = []

    async def compare_opportunities(self, items):
        self.compare_calls.append(items)
        return {"items": items, "matrix": [{"left": "opp_1", "right": "opp_2"}]}


@pytest.mark.asyncio
async def test_compare_accepts_opportunity_ids_and_analysis_ids():
    app = web.Application()
    service = FakeOpportunityService()
    app["opportunity_service"] = service

    from src.api.routes.opportunities import setup_opportunity_routes

    setup_opportunity_routes(app)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        response = await client.post(
            "/opportunities/compare",
            json={
                "items": [
                    {"opportunity_id": "opp_1"},
                    {"analysis_id": "ana_2", "opportunity_id": "opp_2"},
                ]
            },
        )
        payload = await response.json()
    finally:
        await client.close()

    assert response.status == 200
    assert payload["items"][0]["opportunity_id"] == "opp_1"
    assert payload["items"][1]["analysis_id"] == "ana_2"
    assert service.compare_calls == [[{"opportunity_id": "opp_1"}, {"analysis_id": "ana_2", "opportunity_id": "opp_2"}]]


@pytest.mark.asyncio
async def test_real_backend_service_implements_compare_opportunities():
    service = DefiIntelligenceEngine.__new__(DefiIntelligenceEngine)
    setattr(service, "engine", FakeEngine())

    payload = await service.compare_opportunities([
        {"opportunity_id": "opp_1"},
        {"analysis_id": "ana_2", "opportunity_id": "opp_2"},
    ])

    assert payload["matrix"][0]["left"] == "opp_1"
    engine = cast(Any, service.engine)
    assert engine.compare_calls == [[
        {"opportunity_id": "opp_1"},
        {"analysis_id": "ana_2", "opportunity_id": "opp_2"},
    ]]
