"""
aiohttp Application factory for Ilyon AI Web API.

Creates and configures the API application with all routes
and middleware for handling web requests and Blinks.
"""

import logging
from aiohttp import web

from src.api.middleware.cors import cors_middleware
from src.api.middleware.rate_limit import rate_limit_middleware
from src.api.routes.auth import auth_middleware
from src.api.routes.actions import setup_actions_routes
from src.api.routes.blinks import setup_blinks_routes
from src.api.routes.analysis import setup_analysis_routes
from src.api.routes.trending import setup_trending_routes
from src.api.routes.portfolio import setup_portfolio_routes
from src.api.routes.transactions import setup_transactions_routes
from src.api.routes.whale import setup_whale_routes
from src.public_api.router import setup_public_api_routes
from src.api.routes.auth import setup_auth_routes
from src.api.routes.stats import setup_stats_routes
from src.api.routes.chains import setup_chains_routes
from src.api.routes.contracts import setup_contracts_routes
from src.api.routes.shield import setup_shield_routes
from src.api.routes.defi import setup_defi_routes
from src.api.routes.intel import setup_intel_routes
from src.api.routes.opportunities import setup_opportunity_routes
from src.api.routes.smart_money import setup_smart_money_routes
from src.api.routes.stream import setup_stream_routes
from src.api.routes.alerts import setup_alert_routes
from src.agents.sentinel import start_sentinel, stop_sentinel
from src.config import settings

logger = logging.getLogger(__name__)


async def health_check(request: web.Request) -> web.Response:
    """
    GET /health

    Health check endpoint for load balancers and monitoring.
    """
    return web.json_response({
        "status": "healthy",
        "service": "Ilyon AI Web API",
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
        "name": "Ilyon AI API",
        "version": "2.0.0",
        "description": "Multi-chain DeFi intelligence API",
        "supported_chains": [
            "solana", "ethereum", "base", "arbitrum",
            "bsc", "polygon", "optimism", "avalanche"
        ],
        "endpoints": {
            "analyze": "POST /api/v1/analyze",
            "token": "GET /api/v1/token/{address}?chain={chain}",
            "search": "GET /api/v1/search",
            "trending": "GET /api/v1/trending",
            "portfolio": "GET /api/v1/portfolio",
            "whales": "GET /api/v1/whales",
            "shield": "GET /api/v1/shield/{wallet}",
            "contract": "POST /api/v1/contract/scan",
            "pool_analysis": "POST /api/v1/defi/pool/analyze",
            "defi_pools": "GET /api/v1/defi/pools",
            "defi_yields": "GET /api/v1/defi/yields",
            "defi_opportunities": "GET /api/v1/defi/opportunities",
            "defi_protocol_profile": "GET /api/v1/defi/protocol/{slug}",
            "defi_v2_discover": "GET /api/v2/defi/discover",
            "defi_v2_compare": "GET /api/v2/defi/compare",
            "defi_v2_protocol": "GET /api/v2/defi/protocols/{slug}",
            "defi_v2_opportunity": "GET /api/v2/defi/opportunities/{id}",
            "chains": "GET /api/v1/chains",
            "auth": "POST /api/v1/auth/challenge",
        },
        "docs": "/api/v1/docs"
    })


async def api_docs(request: web.Request) -> web.Response:
    """
    GET /api/v1/docs

    Lightweight machine-readable API documentation.
    """
    return web.json_response({
        "name": "Ilyon AI API",
        "version": "2.0.0",
        "base_url": "/api/v1",
        "description": "Multi-chain DeFi intelligence API",
        "core_workflows": {
            "token_analysis": [
                "POST /api/v1/analyze",
                "GET /api/v1/token/{address}?chain={chain}",
                "POST /api/v1/token/{address}/refresh?chain={chain}",
            ],
            "discovery": [
                "GET /api/v1/search?query=...&chain=...",
                "GET /api/v1/chains",
                "GET /api/v1/chains/{chain}",
                "GET /api/v2/defi/discover",
            ],
            "smart_money": [
                "GET /api/v1/smart-money/overview",
            ],
            "alerts": [
                "GET /api/v1/alerts",
            ],
            "security": [
                "POST /api/v1/contract/scan",
                "GET /api/v1/contract/{chain}/{address}",
                "GET /api/v1/shield/{wallet}?chain=...",
                "POST /api/v1/shield/revoke",
            ],
            "defi": [
                "POST /api/v1/defi/pool/analyze",
                "GET /api/v1/defi/pools",
                "GET /api/v1/defi/yields",
                "GET /api/v1/defi/lending",
                "GET /api/v1/defi/opportunities",
                "GET /api/v1/defi/opportunities/{id}",
                "GET /api/v1/defi/protocol/{slug}",
                "GET /api/v2/defi/discover",
                "GET /api/v2/defi/compare?asset=USDC&chain=base",
                "GET /api/v2/defi/protocols/{slug}",
                "GET /api/v2/defi/opportunities/{id}",
                "POST /api/v2/defi/simulate/lp",
                "POST /api/v2/defi/simulate/lending",
                "POST /api/v2/defi/positions/analyze",
            ],
        },
        "examples": {
            "analyze": {
                "request": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "chain": "ethereum", "mode": "standard"},
                "response_fields": ["token", "scores", "market", "security", "holders", "ai", "recommendation"],
            },
            "contract_scan": {
                "request": {"address": "0x1f98431c8aD98523631AE4a59f267346ea31F984", "chain": "ethereum"},
                "response_fields": ["overall_risk", "risk_score", "vulnerabilities", "key_findings", "recommendations"],
            },
        },
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
            auth_middleware,
            rate_limit_middleware,
        ]
    )

    # Health check and info
    app.router.add_get("/health", health_check)
    app.router.add_get("/api/v1", api_info)
    app.router.add_get("/api/v1/docs", api_docs)

    # Setup all routes
    setup_actions_routes(app)
    setup_blinks_routes(app)
    setup_analysis_routes(app)
    setup_trending_routes(app)
    setup_portfolio_routes(app)
    setup_transactions_routes(app)
    setup_whale_routes(app)
    setup_auth_routes(app)
    setup_stats_routes(app)
    setup_chains_routes(app)
    setup_contracts_routes(app)
    setup_shield_routes(app)
    setup_defi_routes(app)
    setup_intel_routes(app)
    setup_opportunity_routes(app)
    setup_smart_money_routes(app)
    setup_stream_routes(app)
    setup_alert_routes(app)
    setup_public_api_routes(app)

    # Background sentinel agent
    app.on_startup.append(start_sentinel)
    app.on_cleanup.append(stop_sentinel)

    logger.info("Ilyon AI Web API application created with all routes")
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
            auth_middleware,
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
    app.router.add_get("/health", health_check)
    app.router.add_get("/api/v1", api_info)
    app.router.add_get("/api/v1/docs", api_docs)
    setup_actions_routes(app)
    setup_blinks_routes(app)
    setup_analysis_routes(app)
    setup_trending_routes(app)
    setup_portfolio_routes(app)
    setup_transactions_routes(app)
    setup_whale_routes(app)
    setup_auth_routes(app)
    setup_stats_routes(app)
    setup_chains_routes(app)
    setup_contracts_routes(app)
    setup_shield_routes(app)
    setup_defi_routes(app)
    setup_intel_routes(app)
    setup_opportunity_routes(app)
    setup_smart_money_routes(app)
    setup_stream_routes(app)
    setup_alert_routes(app)
    setup_public_api_routes(app)

    logger.info("All API routes added to existing application")
