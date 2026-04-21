"""
Agent v2 API routes (feature-flagged stubs).

These stubs return 503 when FEATURE_AGENT_V2 is off,
and 501 (not implemented) when the flag is on but the
real handler hasn't been wired yet.
"""

from aiohttp import web

from src.config import settings

routes = web.RouteTableDef()


def _flag_off() -> web.Response:
    return web.json_response({"error": "agent_v2_disabled"}, status=503)


@routes.post("/api/v1/agent")
async def agent_turn(request: web.Request) -> web.Response:
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    return web.json_response({"error": "not_implemented"}, status=501)


@routes.get("/api/v1/agent/sessions")
async def list_sessions(request: web.Request) -> web.Response:
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    return web.json_response({"error": "not_implemented"}, status=501)


@routes.get("/api/v1/agent/sessions/{session_id}")
async def get_session(request: web.Request) -> web.Response:
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    return web.json_response({"error": "not_implemented"}, status=501)


@routes.post("/api/v1/agent/sessions/{session_id}/messages")
async def post_message(request: web.Request) -> web.Response:
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    return web.json_response({"error": "not_implemented"}, status=501)


def setup_agent_routes(app: web.Application) -> None:
    """Register agent v2 routes on *app*."""
    app.router.add_routes(routes)
