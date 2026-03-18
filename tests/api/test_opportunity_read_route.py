import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from typing import Any, cast

from src.defi.opportunity_engine import DefiOpportunityEngine


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


class FakeAnalysisStore:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def get_opportunity_document(self, opportunity_id: str):
        self.calls.append(opportunity_id)
        return self.payload


class FakeEngine:
    def __init__(self, payload):
        self.analysis_store = FakeAnalysisStore(payload)
        self.fallback_calls = []

    async def get_opportunity(self, opportunity_id: str, include_ai: bool = True, ranking_profile=None):
        raise AssertionError("should use facade forwarding, not nested direct call")

    async def get_opportunity_profile(self, opportunity_id: str, include_ai: bool = True, ranking_profile=None):
        self.fallback_calls.append((opportunity_id, include_ai, ranking_profile))
        return {"identity": {"id": opportunity_id, "source": "fallback"}}


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


@pytest.mark.asyncio
async def test_real_backend_service_reads_materialized_document_before_fallback():
    stored = {
        "identity": {"id": "opp_1", "source": "store"},
        "scores": {"final_deployability_score": 88},
    }
    service = DefiOpportunityEngine.__new__(DefiOpportunityEngine)
    setattr(service, "analysis_store", FakeAnalysisStore(stored))

    async def fake_get_opportunity_profile(opportunity_id: str, include_ai: bool = True, ranking_profile=None):
        raise AssertionError(f"unexpected fallback for {opportunity_id}")

    setattr(service, "get_opportunity_profile", fake_get_opportunity_profile)

    payload = await service.get_opportunity("opp_1")

    assert payload is not None
    assert payload["identity"]["source"] == "store"
    assert cast(Any, service.analysis_store).calls == ["opp_1"]
