"""
Public Developer API Router.

Provides endpoints for developers to integrate Ilyon AI intelligence
into their own dApps, trading bots, and platforms.

Features:
- API key authentication
- Rate limiting
- Webhook management
"""

import logging
from aiohttp import web

logger = logging.getLogger(__name__)

async def get_api_status(request: web.Request) -> web.Response:
    """
    GET /api/public/v1/status
    
    Check Developer API status.
    """
    return web.json_response({
        "status": "online",
        "version": "1.0",
        "features": [
            "token_analysis",
            "wallet_forensics",
            "smart_contract_scan"
        ]
    })

def setup_public_api_routes(app: web.Application):
    """Setup Developer API routes."""
    app.router.add_get('/api/public/v1/status', get_api_status)
    logger.info("Public Developer API routes registered")
