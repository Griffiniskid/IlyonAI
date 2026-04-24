"""
CORS middleware for Ilyon AI Web API.

Supports both Solana Actions (permissive CORS) and Web API (configurable CORS).
"""

from aiohttp import web
from aiohttp.web import middleware

from src.config import settings


# Allowed headers for all routes
ALLOWED_HEADERS = [
    "Content-Type",
    "Accept",
    "Accept-Encoding",
    "Accept-Language",
    "Authorization",
    "X-Action-Version",
    "X-Blockchain-Ids",
    "X-User-Id",
    "X-Requested-With",
]

# Allowed methods
ALLOWED_METHODS = "GET, POST, PUT, DELETE, OPTIONS, PATCH"


def get_cors_origin(request: web.Request) -> str:
    """
    Get appropriate CORS origin based on request path.

    Actions/Blinks routes require * for Twitter unfurling.
    Other routes use configured origins.
    """
    path = request.path

    # Actions/Blinks routes need permissive CORS
    if (path.startswith('/actions') or path.startswith('/blinks/')
            or path.startswith('/api/v1/blinks/')
            or path.startswith('/.well-known/')):
        return "*"

    # For other routes, check against configured origins
    request_origin = request.headers.get('Origin', '')
    allowed_origins = settings.get_cors_origins()

    # If * is in allowed origins, allow all
    if "*" in allowed_origins:
        return "*"

    # Check if request origin is allowed
    if request_origin in allowed_origins:
        return request_origin

    # Default to first configured origin
    return allowed_origins[0] if allowed_origins else "*"


@middleware
async def cors_middleware(request: web.Request, handler):
    """
    CORS middleware for handling cross-origin requests.

    Handles both Actions API (permissive) and Web API (configurable).
    """
    cors_origin = get_cors_origin(request)

    # Handle preflight OPTIONS requests
    if request.method == "OPTIONS":
        response = web.Response(status=204)
        response.headers["Access-Control-Allow-Origin"] = cors_origin
        response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
        response.headers["Access-Control-Allow-Headers"] = ", ".join(ALLOWED_HEADERS)
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Max-Age"] = "86400"  # 24 hours
        return response

    # Handle actual request
    response = await handler(request)

    # Add CORS headers to response
    response.headers["Access-Control-Allow-Origin"] = cors_origin
    response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
    response.headers["Access-Control-Allow-Headers"] = ", ".join(ALLOWED_HEADERS)
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Expose-Headers"] = "Content-Length, Content-Type"

    return response
