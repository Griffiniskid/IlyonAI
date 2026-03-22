import asyncio
from contextlib import asynccontextmanager

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


class _FastLaneOpportunityService:
    async def get_opportunity_analysis(self, analysis_id: str):
        return {
            "analysis_id": analysis_id,
            "status": "running",
            "score_model_version": "defi-v2",
            "provisional_shortlist": [
                {
                    "id": "yield:alpha-usdc",
                    "symbol": "ALPHA/USDC",
                    "chain": "solana",
                    "shortlist_score": 77,
                    "apy": 13.2,
                    "tvlUsd": 1500000,
                }
            ],
            "progress": {"stage": "scan", "percent": 35},
        }


class _FailedFastLaneOpportunityService:
    async def get_opportunity_analysis(self, analysis_id: str):
        return {
            "analysis_id": analysis_id,
            "status": "failed",
            "score_model_version": "defi-v2",
            "provisional_shortlist": [
                {
                    "id": "yield:alpha-usdc",
                    "symbol": "ALPHA/USDC",
                    "chain": "solana",
                    "shortlist_score": 77,
                }
            ],
            "error": "downstream timeout",
        }


@asynccontextmanager
async def _fast_lane_client():
    app = web.Application()
    app["opportunity_service"] = _FastLaneOpportunityService()

    from src.api.routes.opportunities import setup_opportunity_routes

    setup_opportunity_routes(app)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


@asynccontextmanager
async def _failed_fast_lane_client():
    app = web.Application()
    app["opportunity_service"] = _FailedFastLaneOpportunityService()

    from src.api.routes.opportunities import setup_opportunity_routes

    setup_opportunity_routes(app)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


def run_fast_lane_analysis_request():
    async def _run():
        async with _fast_lane_client() as client:
            response = await client.get("/opportunities/analyses/ana_fast")
            return await response.json()

    return asyncio.run(_run())


def run_failed_fast_lane_analysis_request():
    async def _run():
        async with _failed_fast_lane_client() as client:
            response = await client.get("/opportunities/analyses/ana_failed")
            return await response.json()

    return asyncio.run(_run())


def test_opportunity_analysis_returns_fast_lane_snapshot_before_deep_completion():
    response = run_fast_lane_analysis_request()
    assert response["status"] == "ok"
    data = response["data"]
    assert data["status"] in {"scanning", "enriching", "completed"}
    assert "quick_view" in data["data"]


def test_opportunity_analysis_preserves_failed_status_for_fast_lane_snapshot():
    response = run_failed_fast_lane_analysis_request()
    assert response["status"] == "ok"
    data = response["data"]
    assert data["status"] == "failed"
    assert "quick_view" in data["data"]
