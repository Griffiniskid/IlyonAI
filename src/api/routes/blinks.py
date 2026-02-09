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


async def create_new_blink(request: web.Request) -> web.Response:
    """
    POST /api/v1/blinks/create

    Create a new Blink for a token.
    """
    try:
        data = await request.json()
        token_address = data.get("token_address")

        if not token_address:
            return web.json_response(
                {"error": "Token address required"},
                status=400,
            )

        # Get shared analyzer from app context (set by analysis routes on startup)
        analyzer = request.app.get('analyzer')
        if not analyzer:
            logger.error("Analyzer not found in app context - cannot create blink")
            return web.json_response(
                {"error": "Service not ready. Please try again in a moment."},
                status=503,
            )

        # Use "quick" mode for blink creation
        result = await analyzer.analyze(token_address, mode="quick")

        if not result:
            return web.json_response(
                {"error": "Could not analyze token"},
                status=500,
            )

        blink_service = get_blink_service()
        blink_data = await blink_service.create_blink(
            token_address=token_address,
            analysis_result=result
        )

        return web.json_response(blink_data)

    except Exception as e:
        logger.error(f"Error creating blink: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e)},
            status=500,
        )


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
                "Cache-Control": "public, max-age=300",  # Cache 5 minutes
            },
        )

    except ValueError as e:
        logger.warning(f"Blink not found: {blink_id} - {e}")
        return web.json_response(
            {"error": str(e)},
            status=404,
        )
    except Exception as e:
        logger.error(f"Error getting blink {blink_id}: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error"},
            status=500,
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

        return web.json_response(result)

    except ValueError as e:
        logger.warning(f"Blink not found for execution: {blink_id} - {e}")
        return web.json_response(
            {"error": str(e)},
            status=404,
        )
    except Exception as e:
        logger.error(f"Error executing blink {blink_id}: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal server error"},
            status=500,
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
                "Cache-Control": "public, max-age=300",
            },
        )

    except ValueError as e:
        logger.warning(f"Blink not found for icon: {blink_id}")
        icon_generator = get_icon_generator()
        default_icon = icon_generator.generate_default()
        return web.Response(
            body=default_icon.read(),
            content_type="image/png",
            headers={"Cache-Control": "public, max-age=60"},
        )
    except Exception as e:
        logger.error(f"Error generating icon for {blink_id}: {e}", exc_info=True)
        icon_generator = get_icon_generator()
        default_icon = icon_generator.generate_default()
        return web.Response(
            body=default_icon.read(),
            content_type="image/png",
            headers={"Cache-Control": "public, max-age=60"},
        )


async def blink_redirect(request: web.Request) -> web.Response:
    """
    GET /blinks/{blink_id}

    Redirect shareable URL to web app token page.
    """
    blink_id = request.match_info["blink_id"]

    try:
        blink_service = get_blink_service()
        blink = await blink_service.get_blink(blink_id)

        if blink:
            # Build redirect URL first, before anything that can fail
            redirect_url = f"{settings.webapp_url}/token/{blink.token_address}"

            # Track view event (fire-and-forget, don't block redirect)
            try:
                await blink_service.track_event(
                    blink_id=blink_id,
                    event_type="view",
                    ip_hash=request.get("ip_hash"),
                    user_agent=request.headers.get("User-Agent", ""),
                    referrer=request.headers.get("Referer", ""),
                )
            except Exception as track_err:
                logger.warning(f"Failed to track blink view {blink_id}: {track_err}")

            raise web.HTTPFound(location=redirect_url)

        # Not found - redirect to home
        raise web.HTTPFound(location=settings.webapp_url)

    except web.HTTPFound:
        raise
    except Exception as e:
        logger.error(f"Error redirecting blink {blink_id}: {e}")
        raise web.HTTPFound(location=settings.webapp_url)


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
    app.router.add_post("/api/v1/blinks/create", create_new_blink)
    app.router.add_options("/api/v1/blinks/create", options_handler)
    app.router.add_get("/api/v1/blinks/{blink_id}", get_blink)
    app.router.add_post("/api/v1/blinks/{blink_id}", execute_blink)
    app.router.add_options("/api/v1/blinks/{blink_id}", options_handler)

    # Icon endpoint
    app.router.add_get("/api/v1/blinks/{blink_id}/icon.png", get_blink_icon)

    # Shareable URL redirect
    app.router.add_get("/blinks/{blink_id}", blink_redirect)

    logger.info("Blinks routes registered")
