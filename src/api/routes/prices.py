"""Generic CoinGecko `simple/price` proxy for the frontend.

Cloudflare blocks `/api/coingecko/*` rewrites at the edge (Phase A v1 found
this — staging.ilyonai.com / Cloudflare returns 403 on that path before the
request reaches Next). And calling CoinGecko directly from the browser is
CORS-blocked. So the frontend (MarketTickerBar, SidebarMarketList,
MainApp's price poller) needs a server-side proxy:

  * uses the shared price client (already authenticated where applicable)
  * 60s in-memory TTL cache per `(ids, vs_currencies, include_24h)` key
  * silently degrades to {} on upstream failure — the frontend wraps in
    try/catch so the ticker stays empty rather than throwing pageerrors

Endpoint shape mirrors CoinGecko's `simple/price` so the client code can
swap URL only.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

_CACHE: dict[tuple, tuple[float, dict]] = {}
_CACHE_TTL = 60.0  # seconds


def _cache_key(ids: str, vs: str, include_24h: bool) -> tuple:
    return (ids, vs, include_24h)


async def _fetch_prices(ids: str, vs: str, include_24h: bool) -> dict[str, Any]:
    """Server-side fetch via the shared price client. Returns {} on failure."""
    try:
        from src.agent.services import get_agent_services

        services = await get_agent_services()
        price_client = services.price
        if price_client is None:
            return {}
        id_list = [s.strip() for s in ids.split(",") if s.strip()]
        if not id_list:
            return {}
        data = await price_client.get_token_price(id_list, vs_currencies=vs)
        if not isinstance(data, dict):
            return {}
        # If the caller didn't ask for 24h change, strip it to keep payload tight.
        if not include_24h:
            return {
                k: {kk: vv for kk, vv in v.items() if kk == vs}
                if isinstance(v, dict) else v
                for k, v in data.items()
            }
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("prices proxy fetch failed (ids=%s): %s", ids[:80], exc)
        return {}


routes = web.RouteTableDef()


@routes.get("/api/v1/prices/simple")
async def simple_price(request: web.Request) -> web.Response:
    """Proxy `GET /api/v3/simple/price` with cache + silent fallback.

    Query params:
      ids                  comma-separated CoinGecko IDs (required)
      vs_currencies        default 'usd'
      include_24hr_change  'true' to include 24h % change
    """
    ids = request.query.get("ids", "").strip()
    if not ids:
        return web.json_response({})
    vs = request.query.get("vs_currencies", "usd").strip().lower() or "usd"
    include_24h = request.query.get("include_24hr_change", "").lower() in {"true", "1", "yes"}
    key = _cache_key(ids, vs, include_24h)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL:
        return web.json_response(cached[1], headers={"x-cache": "HIT"})
    data = await _fetch_prices(ids, vs, include_24h)
    if data:
        _CACHE[key] = (now, data)
        return web.json_response(data, headers={"x-cache": "MISS"})
    # On upstream failure: serve stale cache if any, else empty dict (NOT 5xx).
    if cached:
        return web.json_response(cached[1], headers={"x-cache": "STALE"})
    return web.json_response({}, headers={"x-cache": "EMPTY"})


def setup_prices_routes(app: web.Application) -> None:
    """Register price proxy routes on *app*."""
    app.router.add_routes(routes)
