"""
Tokens ticker bar API route (feature-flagged stub).

Returns 503 when FEATURE_TOKENS_BAR is off,
and 501 (not implemented) when the flag is on.
"""

from aiohttp import web

from src.config import settings

routes = web.RouteTableDef()


@routes.get("/api/v1/tokens/ticker")
async def ticker(request: web.Request) -> web.Response:
    if not settings.FEATURE_TOKENS_BAR:
        return web.json_response({"error": "tokens_bar_disabled"}, status=503)
    return web.json_response({"error": "not_implemented"}, status=501)


def setup_tokens_bar_routes(app: web.Application) -> None:
    """Register tokens bar routes on *app*."""
    app.router.add_routes(routes)
