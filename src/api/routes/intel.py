"""
Intelligence Platform API routes: REKT database and Audit database.

GET /api/v1/intel/rekt              - List DeFi hack/exploit incidents
GET /api/v1/intel/rekt/{id}         - Single incident detail
GET /api/v1/intel/audits            - List smart contract audits
GET /api/v1/intel/audits/{id}       - Single audit detail
GET /api/v1/intel/stats             - Aggregate intelligence stats
"""

import logging
from typing import Optional

from aiohttp import web

from src.api.response_envelope import make_envelope
from src.api.response_envelope import envelope_error_response, envelope_response
from src.intel.rekt_database import RektDatabase, AuditDatabase

logger = logging.getLogger(__name__)

_rekt: Optional[RektDatabase] = None
_audits: Optional[AuditDatabase] = None


async def init_intel(app: web.Application):
    global _rekt, _audits
    _rekt = RektDatabase()
    _audits = AuditDatabase()
    logger.info("Intel databases initialized")


async def cleanup_intel(app: web.Application):
    global _rekt, _audits
    if _rekt:
        await _rekt.close()
    if _audits:
        await _audits.close()
    logger.info("Intel databases closed")


async def list_rekt(request: web.Request) -> web.Response:
    """
    GET /api/v1/intel/rekt

    List DeFi security incidents (hacks, exploits, rug pulls).

    Query params:
      chain       - Filter by chain name
      attack_type - Filter by attack vector (e.g. "Flash Loan", "Rug Pull")
      min_amount  - Minimum USD amount stolen
      search      - Full-text search across name, protocol, description
      limit       - Max results (default: 50)
    """
    if _rekt is None:
        return envelope_error_response(
            "Intel database not available",
            code="SERVICE_UNAVAILABLE",
            http_status=503,
        )

    q = request.rel_url.query
    chain = q.get("chain")
    attack_type = q.get("attack_type")
    search = q.get("search") or q.get("q")
    try:
        min_amount = float(q.get("min_amount", "0"))
        limit = min(int(q.get("limit", "50")), 500)
    except (ValueError, TypeError):
        return envelope_error_response(
            "Invalid numeric query parameter",
            code="INVALID_QUERY",
            http_status=400,
        )

    if min_amount < 0:
        return envelope_error_response("min_amount must be >= 0", code="INVALID_QUERY", http_status=400)
    if limit < 0:
        return envelope_error_response("limit must be >= 0", code="INVALID_QUERY", http_status=400)

    try:
        incidents = await _rekt.get_incidents(
            chain=chain,
            attack_type=attack_type,
            min_amount=min_amount,
            search=search,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"REKT query error: {e}")
        return envelope_error_response(
            "Failed to query incident database",
            code="QUERY_FAILED",
            http_status=500,
        )

    total_stolen = sum(i.get("amount_usd") or 0 for i in incidents)
    freshness_info = _rekt.get_freshness()

    return envelope_response(
        data={
            "incidents": incidents,
            "count": len(incidents),
            "total_stolen_usd": total_stolen,
            "filters": {
                "chain": chain,
                "attack_type": attack_type,
                "min_amount": min_amount,
                "search": search,
            },
        },
        meta={
            "cursor": None,
            "freshness": freshness_info.get("source", "unknown"),
            "data_freshness": freshness_info,
        },
        freshness=freshness_info.get("source", "unknown"),
    )


async def get_rekt_incident(request: web.Request) -> web.Response:
    """
    GET /api/v1/intel/rekt/{id}

    Fetch a single incident by its ID.
    """
    if _rekt is None:
        return web.json_response({"error": "Intel database not available"}, status=503)

    incident_id = request.match_info.get("id", "").strip()
    if not incident_id:
        return web.json_response({"error": "incident id required"}, status=400)

    try:
        incident = await _rekt.get_incident(incident_id)
    except Exception as e:
        logger.error(f"REKT detail error for {incident_id}: {e}")
        return web.json_response({"error": "Failed to fetch incident"}, status=500)

    if not incident:
        return web.json_response({"error": f"Incident '{incident_id}' not found"}, status=404)

    return web.json_response(make_envelope(
        data=incident,
        meta={
            "freshness": "warm",
        },
        freshness="warm",
    ))


async def list_audits(request: web.Request) -> web.Response:
    """
    GET /api/v1/intel/audits

    List smart contract audit records.

    Query params:
      protocol - Filter by protocol name
      auditor  - Filter by audit firm
      chain    - Filter by chain
      verdict  - PASS or FAIL
      limit    - Max results (default: 50)
    """
    if _audits is None:
        return web.json_response({"error": "Intel database not available"}, status=503)

    q = request.rel_url.query
    protocol = q.get("protocol")
    auditor = q.get("auditor")
    chain = q.get("chain")
    verdict = q.get("verdict")
    try:
        limit = min(int(q.get("limit", "50")), 500)
    except (ValueError, TypeError):
        limit = 50

    if verdict and verdict.upper() not in ("PASS", "FAIL"):
        return web.json_response({"error": "verdict must be PASS or FAIL"}, status=400)

    try:
        audit_list = await _audits.get_audits(
            protocol=protocol,
            auditor=auditor,
            chain=chain,
            verdict=verdict,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Audit query error: {e}")
        return web.json_response({"error": "Failed to query audit database"}, status=500)

    audit_freshness = _audits.get_freshness()
    return web.json_response({
        "audits": audit_list,
        "count": len(audit_list),
        "filters": {
            "protocol": protocol,
            "auditor": auditor,
            "chain": chain,
            "verdict": verdict,
        },
        "data_freshness": audit_freshness,
    })


async def get_audit_detail(request: web.Request) -> web.Response:
    """
    GET /api/v1/intel/audits/{id}

    Fetch a single audit record by ID.
    """
    if _audits is None:
        return web.json_response({"error": "Intel database not available"}, status=503)

    audit_id = request.match_info.get("id", "").strip()
    if not audit_id:
        return web.json_response({"error": "audit id required"}, status=400)

    try:
        audit = await _audits.get_audit(audit_id)
    except Exception as e:
        logger.error(f"Audit detail error for {audit_id}: {e}")
        return web.json_response({"error": "Failed to fetch audit"}, status=500)

    if not audit:
        return web.json_response({"error": f"Audit '{audit_id}' not found"}, status=404)

    return web.json_response(audit)


async def get_intel_stats(request: web.Request) -> web.Response:
    """
    GET /api/v1/intel/stats

    Aggregate statistics from the intelligence platform.
    """
    if _rekt is None or _audits is None:
        return web.json_response({"error": "Intel database not available"}, status=503)

    try:
        all_incidents = await _rekt.get_incidents(limit=10000)
        all_audits = await _audits.get_audits(limit=10000)
    except Exception as e:
        logger.error(f"Intel stats error: {e}")
        return web.json_response({"error": "Failed to compute stats"}, status=500)

    total_stolen = sum(i.get("amount_usd") or 0 for i in all_incidents)
    recovered = sum(
        i.get("amount_usd") or 0
        for i in all_incidents
        if i.get("funds_recovered")
    )

    attack_types: dict = {}
    for i in all_incidents:
        at = i.get("attack_type") or "Unknown"
        attack_types[at] = attack_types.get(at, 0) + 1

    chains_hit: dict = {}
    for i in all_incidents:
        for c in (i.get("chains") or []):
            chains_hit[c] = chains_hit.get(c, 0) + 1

    return web.json_response({
        "rekt": {
            "total_incidents": len(all_incidents),
            "total_stolen_usd": total_stolen,
            "total_recovered_usd": recovered,
            "recovery_rate": round(recovered / total_stolen, 4) if total_stolen > 0 else 0,
            "top_attack_types": sorted(
                [{"type": k, "count": v} for k, v in attack_types.items()],
                key=lambda x: x["count"], reverse=True
            )[:10],
            "chains_most_hit": sorted(
                [{"chain": k, "count": v} for k, v in chains_hit.items()],
                key=lambda x: x["count"], reverse=True
            )[:10],
        },
        "audits": {
            "total_audits": len(all_audits),
            "pass_count": sum(1 for a in all_audits if a.get("verdict") == "PASS"),
            "fail_count": sum(1 for a in all_audits if a.get("verdict") == "FAIL"),
        },
    })


def setup_intel_routes(app: web.Application):
    """Register Intelligence Platform routes and lifecycle hooks."""
    app.on_startup.append(init_intel)
    app.on_cleanup.append(cleanup_intel)

    app.router.add_get("/api/v1/intel/rekt", list_rekt)
    app.router.add_get("/api/v1/intel/rekt/{id}", get_rekt_incident)
    app.router.add_get("/api/v1/intel/audits", list_audits)
    app.router.add_get("/api/v1/intel/audits/{id}", get_audit_detail)
    app.router.add_get("/api/v1/intel/stats", get_intel_stats)

    logger.info("Intel routes registered")
