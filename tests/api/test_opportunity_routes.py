from contextlib import asynccontextmanager

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


class FakeOpportunityService:
    def __init__(self):
        self.start_calls = []

    async def start_opportunity_analysis(self, **filters):
        self.start_calls.append(filters)
        return {
            "analysis_id": "ana_123",
            "status": "running",
            "score_model_version": "defi-v2",
            "freshness": {"generated_at": "2026-03-17T00:00:00Z"},
            "provisional_shortlist": [],
            "progress": {"stage": "scan", "percent": 25},
            "metrics": {"requests": 1},
        }

    async def get_opportunity_analysis(self, analysis_id: str):
        return {
            "analysis_id": analysis_id,
            "status": "completed",
            "score_model_version": "defi-v2",
            "freshness": {"generated_at": "2026-03-17T00:00:10Z"},
            "provisional_shortlist": [],
            "progress": {"stage": "completed", "percent": 100},
            "metrics": {"requests": 2},
            "result": {
                "identity": {"id": "opp_1"},
                "recommendation": {"action": "watch", "rationale": ["completed payload"]},
            },
        }


@asynccontextmanager
async def opportunity_client():
    app = web.Application()
    app["opportunity_service"] = FakeOpportunityService()

    from src.api.routes.opportunities import setup_opportunity_routes

    setup_opportunity_routes(app)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_create_opportunity_analysis_returns_analysis_id():
    async with opportunity_client() as client:
        response = await client.post("/opportunities/analyses", json={"chain": "solana", "limit": 5})
        payload = await response.json()

        assert response.status == 202
        assert payload["analysis_id"] == "ana_123"
        assert payload["score_model_version"] == "defi-v2"
        assert payload["freshness"]["generated_at"] == "2026-03-17T00:00:00Z"
        assert payload["provisional_shortlist"] == []
        assert payload["progress"]["stage"] == "scan"
        assert payload["metrics"] == {"requests": 1}

        second = await client.post("/opportunities/analyses", json={"chain": "solana", "limit": 5})
        second_payload = await second.json()

        assert second_payload["analysis_id"] == payload["analysis_id"]


@pytest.mark.asyncio
async def test_get_opportunity_analysis_returns_completed_result():
    async with opportunity_client() as client:
        response = await client.get("/opportunities/analyses/ana_123")
        payload = await response.json()

        assert response.status == 200
        assert payload["analysis_id"] == "ana_123"
        assert payload["status"] == "completed"
        assert payload["score_model_version"] == "defi-v2"
        assert payload["freshness"]["generated_at"] == "2026-03-17T00:00:10Z"
        assert payload["progress"]["percent"] == 100
        assert payload["metrics"] == {"requests": 2}
        assert payload["result"]["identity"]["id"] == "opp_1"
