"""
Solana Actions manifest endpoint.

Provides the actions.json file required by the Solana Actions spec
for Twitter/X unfurling.
"""

import logging
from aiohttp import web

from src.config import settings

logger = logging.getLogger(__name__)


async def actions_json(request: web.Request) -> web.Response:
    """
    GET /.well-known/actions.json or /actions.json

    Returns the Solana Actions manifest declaring API endpoints.
    """
    manifest = {
        "rules": [
            {
                "pathPattern": "/blinks/*",
                "apiPath": "/api/v1/blinks/*",
            },
            {
                "pathPattern": "/api/v1/blinks/*",
                "apiPath": "/api/v1/blinks/*",
            },
        ],
    }

    return web.json_response(
        manifest,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        },
    )


async def actions_get(request: web.Request) -> web.Response:
    """
    GET /actions

    Returns extended actions manifest with metadata.
    """
    manifest = {
        "name": "AI Sentinel",
        "description": "Solana Token Security Analysis - Verify tokens before you buy",
        "icon": f"{settings.actions_base_url}/static/icon.png",
        "rules": [
            {
                "pathPattern": "/blinks/*",
                "apiPath": "/api/v1/blinks/*",
            },
        ],
        "actions": {
            "verify": {
                "label": "Verify Token",
                "description": "Run fresh security analysis on this Solana token",
            },
        },
    }

    return web.json_response(
        manifest,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )


def setup_actions_routes(app: web.Application):
    """
    Setup actions manifest routes.

    Args:
        app: aiohttp Application to add routes to
    """
    # Standard Solana Actions manifest location
    app.router.add_get("/.well-known/actions.json", actions_json)

    # Alternative locations
    app.router.add_get("/actions.json", actions_json)
    app.router.add_get("/actions", actions_get)

    logger.info("Actions routes registered")
