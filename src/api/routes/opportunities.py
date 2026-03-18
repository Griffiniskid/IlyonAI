"""Opportunity analysis API routes."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from src.api.schemas.requests import OpportunityAnalysisCreateRequest, OpportunityCompareRequest
from src.api.schemas.responses import ErrorResponse, OpportunityAnalysisStatusResponse, OpportunityCompareResponse

logger = logging.getLogger(__name__)


def _get_opportunity_service(request: web.Request) -> Any:
    return request.app.get("opportunity_service") or request.app.get("defi_intelligence_engine")


def _json_error(error: str, code: str, status: int) -> web.Response:
    return web.json_response(ErrorResponse(error=error, code=code).model_dump(mode="json"), status=status)


def _normalize_analysis_status(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("freshness", {})
    normalized.setdefault("provisional_shortlist", [])
    normalized.setdefault("progress", {})
    normalized.setdefault("metrics", normalized.pop("observability", {}) or {})
    return OpportunityAnalysisStatusResponse.model_validate(normalized).model_dump(mode="json")


async def create_opportunity_analysis(request: web.Request) -> web.Response:
    service = _get_opportunity_service(request)
    if service is None or not hasattr(service, "start_opportunity_analysis"):
        return _json_error("Opportunity service unavailable", "SERVICE_UNAVAILABLE", 503)

    try:
        payload = OpportunityAnalysisCreateRequest.model_validate(await request.json()).model_dump()
    except Exception:
        return _json_error("Invalid request", "INVALID_REQUEST", 400)

    status = await service.start_opportunity_analysis(**payload)
    return web.json_response(_normalize_analysis_status(status), status=202)


async def get_opportunity_analysis(request: web.Request) -> web.Response:
    service = _get_opportunity_service(request)
    if service is None or not hasattr(service, "get_opportunity_analysis"):
        return _json_error("Opportunity service unavailable", "SERVICE_UNAVAILABLE", 503)

    analysis_id = request.match_info["analysis_id"]
    status = await service.get_opportunity_analysis(analysis_id)
    if status is None:
        return _json_error("Opportunity analysis not found", "NOT_FOUND", 404)

    return web.json_response(_normalize_analysis_status(status))


async def get_opportunity(request: web.Request) -> web.Response:
    service = _get_opportunity_service(request)
    if service is None:
        return _json_error("Opportunity service unavailable", "SERVICE_UNAVAILABLE", 503)

    opportunity_id = request.match_info["opportunity_id"]
    if hasattr(service, "get_opportunity"):
        payload = await service.get_opportunity(opportunity_id)
    elif hasattr(service, "get_opportunity_profile"):
        payload = await service.get_opportunity_profile(opportunity_id)
    else:
        payload = None

    if payload is None:
        return _json_error("Opportunity not found", "NOT_FOUND", 404)

    return web.json_response(payload)


async def compare_opportunities(request: web.Request) -> web.Response:
    service = _get_opportunity_service(request)
    if service is None or not hasattr(service, "compare_opportunities"):
        return _json_error("Opportunity service unavailable", "SERVICE_UNAVAILABLE", 503)

    try:
        payload = OpportunityCompareRequest.model_validate(await request.json())
    except Exception:
        return _json_error("Invalid request", "INVALID_REQUEST", 400)

    result = await service.compare_opportunities([
        item.model_dump(exclude_none=True) for item in payload.items
    ])
    return web.json_response(OpportunityCompareResponse.model_validate(result).model_dump(mode="json"))


def setup_opportunity_routes(app: web.Application):
    """Register opportunity analysis routes."""

    app.router.add_post("/opportunities/analyses", create_opportunity_analysis)
    app.router.add_get("/opportunities/analyses/{analysis_id}", get_opportunity_analysis)
    app.router.add_get("/opportunities/{opportunity_id}", get_opportunity)
    app.router.add_post("/opportunities/compare", compare_opportunities)

    logger.info("Opportunity routes registered")
