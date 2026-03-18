import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


class FakeOpportunityService:
    async def get_opportunity(self, opportunity_id: str):
        return {
            "identity": {
                "id": opportunity_id,
                "chain": "solana",
                "kind": "pool",
                "protocol_slug": "orca",
            },
            "scores": {"final_deployability_score": 72},
            "behavior": {"whale_flow_direction": "accumulating"},
            "recommendation": {"action": "watch", "rationale": ["waiting on more evidence"]},
            "evidence": {"freshness": {"generated_at": "2026-03-17T00:00:20Z"}},
        }


@pytest.mark.asyncio
async def test_get_opportunity_reads_latest_completed_document():
    app = web.Application()
    app["opportunity_service"] = FakeOpportunityService()

    from src.api.routes.opportunities import setup_opportunity_routes

    setup_opportunity_routes(app)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        response = await client.get("/opportunities/opp_1")
        payload = await response.json()
    finally:
        await client.close()

    assert response.status == 200
    assert payload["identity"]["id"] == "opp_1"
    assert payload["scores"]["final_deployability_score"] == 72
    assert payload["evidence"]["freshness"]["generated_at"] == "2026-03-17T00:00:20Z"
