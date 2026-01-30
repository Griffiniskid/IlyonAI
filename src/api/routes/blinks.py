"""
Blink API endpoints following Solana Actions spec.

Provides endpoints for:
- GET /api/v1/blinks/{id} - Metadata for Twitter unfurling
- POST /api/v1/blinks/{id} - Execute verify action
- GET /api/v1/blinks/{id}/icon.png - Dynamic score icon
- GET /blinks/{id} - Redirect to Telegram bot
"""

import logging
from aiohttp import web

from src.api.services.blink_service import get_blink_service
from src.api.services.icon_generator import get_icon_generator
from src.config import settings

logger = logging.getLogger(__name__)


async def get_blink(request: web.Request) -> web.Response:
    """
    GET /api/v1/blinks/{blink_id}

    Returns Solana Actions metadata for Twitter unfurling.
    """
    blink_id = request.match_info["blink_id"]

    try:
        blink_service = get_blink_service()
        metadata = await blink_service.get_metadata(blink_id)

        # Track view event
        await blink_service.track_event(
            blink_id=blink_id,
            event_type="view",
            ip_hash=request.get("ip_hash"),
            user_agent=request.headers.get("User-Agent", ""),
            referrer=request.headers.get("Referer", ""),
        )

        return web.json_response(
            metadata,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Cache-Control": "public, max-age=300",  # Cache 5 minutes
            },
        )

    except ValueError as e:
        logger.warning(f"Blink not found: {blink_id} - {e}")
        return web.json_response(
            {"error": str(e)},
            status=404,
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logger.error(f"Error getting blink {blink_id}: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error"},
            status=500,
            headers={"Access-Control-Allow-Origin": "*"},
        )


async def execute_blink(request: web.Request) -> web.Response:
    """
    POST /api/v1/blinks/{blink_id}

    Execute the verify action - runs fresh analysis.
    """
    blink_id = request.match_info["blink_id"]

    # Parse request body
    try:
        body = await request.json() if request.body_exists else {}
    except Exception:
        body = {}

    try:
        blink_service = get_blink_service()
        result = await blink_service.execute_verify(
            blink_id=blink_id,
            body=body,
            ip_hash=request.get("ip_hash"),
        )

        # Track verification event
        await blink_service.track_event(
            blink_id=blink_id,
            event_type="verify",
            ip_hash=request.get("ip_hash"),
            user_agent=request.headers.get("User-Agent", ""),
            referrer=request.headers.get("Referer", ""),
        )

        return web.json_response(
            result,
            headers={
                "Access-Control-Allow-Origin": "*",
            },
        )

    except ValueError as e:
        logger.warning(f"Blink not found for execution: {blink_id} - {e}")
        return web.json_response(
            {"error": str(e)},
            status=404,
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logger.error(f"Error executing blink {blink_id}: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error"},
            status=500,
            headers={"Access-Control-Allow-Origin": "*"},
        )


async def get_blink_icon(request: web.Request) -> web.Response:
    """
    GET /api/v1/blinks/{blink_id}/icon.png

    Returns dynamically generated icon with score badge.
    """
    blink_id = request.match_info["blink_id"]

    try:
        icon_generator = get_icon_generator()
        icon_bytes = await icon_generator.generate_for_blink(blink_id)

        return web.Response(
            body=icon_bytes.read(),
            content_type="image/png",
            headers={
                "Cache-Control": "public, max-age=300",  # Cache 5 minutes
                "Access-Control-Allow-Origin": "*",
            },
        )

    except ValueError as e:
        logger.warning(f"Blink not found for icon: {blink_id}")
        # Return default icon
        icon_generator = get_icon_generator()
        default_icon = icon_generator.generate_default()
        return web.Response(
            body=default_icon.read(),
            content_type="image/png",
            headers={
                "Cache-Control": "public, max-age=60",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except Exception as e:
        logger.error(f"Error generating icon for {blink_id}: {e}", exc_info=True)
        # Return default icon on error
        icon_generator = get_icon_generator()
        default_icon = icon_generator.generate_default()
        return web.Response(
            body=default_icon.read(),
            content_type="image/png",
            headers={
                "Cache-Control": "public, max-age=60",
                "Access-Control-Allow-Origin": "*",
            },
        )


async def blink_redirect(request: web.Request) -> web.Response:
    """
    GET /blinks/{blink_id}

    Redirect shareable URL to Telegram bot deep link.
    """
    blink_id = request.match_info["blink_id"]

    try:
        blink_service = get_blink_service()
        blink = await blink_service.get_blink(blink_id)

        if blink:
            # Redirect to Telegram bot with deep link
            telegram_url = f"https://t.me/aisentinelbot?start=blink_{blink_id}"
            raise web.HTTPFound(location=telegram_url)

        # Not found - redirect to bot anyway
        raise web.HTTPFound(location="https://t.me/aisentinelbot")

    except web.HTTPFound:
        raise
    except Exception as e:
        logger.error(f"Error redirecting blink {blink_id}: {e}")
        raise web.HTTPFound(location="https://t.me/aisentinelbot")


async def options_handler(request: web.Request) -> web.Response:
    """
    OPTIONS handler for CORS preflight requests.
    """
    return web.Response(
        status=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Accept, X-Action-Version, X-Blockchain-Ids",
            "Access-Control-Max-Age": "86400",
        },
    )


def setup_blinks_routes(app: web.Application):
    """
    Setup blinks API routes.

    Args:
        app: aiohttp Application to add routes to
    """
    # Main API endpoints
    app.router.add_get("/api/v1/blinks/{blink_id}", get_blink)
    app.router.add_post("/api/v1/blinks/{blink_id}", execute_blink)
    app.router.add_options("/api/v1/blinks/{blink_id}", options_handler)

    # Icon endpoint
    app.router.add_get("/api/v1/blinks/{blink_id}/icon.png", get_blink_icon)

    # Shareable URL redirect
    app.router.add_get("/blinks/{blink_id}", blink_redirect)

    logger.info("Blinks routes registered")
