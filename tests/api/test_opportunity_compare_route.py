import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


class FakeOpportunityService:
    def __init__(self):
        self.compare_calls = []

    async def compare_opportunities(self, items):
        self.compare_calls.append(items)
        return {"items": items, "matrix": []}


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
