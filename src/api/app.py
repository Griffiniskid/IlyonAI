"""
aiohttp Application factory for AI Sentinel Web API.

Creates and configures the API application with all routes
and middleware for handling web requests and Blinks.
"""

import logging
from aiohttp import web

from src.api.middleware.cors import cors_middleware
from src.api.middleware.rate_limit import rate_limit_middleware
from src.api.routes.actions import setup_actions_routes
from src.api.routes.blinks import setup_blinks_routes
from src.api.routes.analysis import setup_analysis_routes
from src.api.routes.trending import setup_trending_routes
from src.api.routes.portfolio import setup_portfolio_routes
from src.api.routes.whale import setup_whale_routes
from src.api.routes.auth import setup_auth_routes
from src.api.routes.stats import setup_stats_routes
from src.config import settings

logger = logging.getLogger(__name__)


async def health_check(request: web.Request) -> web.Response:
    """
    GET /health

    Health check endpoint for load balancers and monitoring.
    """
    return web.json_response({
        "status": "healthy",
        "service": "AI Sentinel Web API",
        "version": "2.0.0",
        "blinks_enabled": settings.blinks_enabled,
        "web_api_enabled": True,
    })


async def api_info(request: web.Request) -> web.Response:
    """
    GET /api/v1

    API information endpoint.
    """
    return web.json_response({
        "name": "AI Sentinel API",
        "version": "1.0.0",
        "description": "Solana token security analysis API",
        "endpoints": {
            "analyze": "POST /api/v1/analyze",
            "token": "GET /api/v1/token/{address}",
            "trending": "GET /api/v1/trending",
            "portfolio": "GET /api/v1/portfolio",
            "whales": "GET /api/v1/whales",
            "auth": "POST /api/v1/auth/challenge",
        },
        "docs": "/api/v1/docs"
    })


def create_api_app() -> web.Application:
    """
    Create and configure the full Web API application.

    Returns:
        Configured aiohttp Application with all routes
    """
    # Create app with middleware
    app = web.Application(
        middlewares=[
            cors_middleware,
            rate_limit_middleware,
        ]
    )

    # Health check and info
    app.router.add_get("/health", health_check)
    app.router.add_get("/api/v1", api_info)

    # Setup all routes
    setup_actions_routes(app)
    setup_blinks_routes(app)
    setup_analysis_routes(app)
    setup_trending_routes(app)
    setup_portfolio_routes(app)
    setup_whale_routes(app)
    setup_auth_routes(app)
    setup_stats_routes(app)

    logger.info("AI Sentinel Web API application created with all routes")
    return app


def create_blinks_only_app() -> web.Application:
    """
    Create a minimal app with only Blinks routes.

    For backward compatibility with existing Blinks deployments.

    Returns:
        Configured aiohttp Application with Blinks routes only
    """
    app = web.Application(
        middlewares=[
            cors_middleware,
            rate_limit_middleware,
        ]
    )

    app.router.add_get("/health", health_check)
    setup_actions_routes(app)
    setup_blinks_routes(app)

    logger.info("Blinks-only API application created")
    return app


def setup_api_routes(app: web.Application):
    """
    Setup all API routes on an existing application.

    Used when integrating with the webhook server.

    Args:
        app: Existing aiohttp Application to add routes to
    """
    # Setup all routes
    setup_actions_routes(app)
    setup_blinks_routes(app)
    setup_analysis_routes(app)
    setup_trending_routes(app)
    setup_portfolio_routes(app)
    setup_whale_routes(app)
    setup_auth_routes(app)
    setup_stats_routes(app)

    logger.info("All API routes added to existing application")
