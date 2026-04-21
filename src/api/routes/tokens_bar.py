from aiohttp import web
from src.config import settings
from src.defi.sentinel_lite import sentinel_lite
import time

_CACHE: dict = {"data": None, "ts": 0}
_CACHE_TTL = 30


async def _fetch_ticker():
    """Fetch top tokens — placeholder until PriceService wired."""
    tokens = [
        {"symbol": "BTC", "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "chain": "ethereum", "price_usd": "67500", "change_24h_pct": 2.1},
        {"symbol": "ETH", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "chain": "ethereum", "price_usd": "3450", "change_24h_pct": 1.5},
        {"symbol": "SOL", "address": "So11111111111111111111111111111111111111112", "chain": "solana", "price_usd": "178", "change_24h_pct": 3.2},
        {"symbol": "BNB", "address": "0xB8c77482e45F1F44dE1745F52C74426C631bDD52", "chain": "bsc", "price_usd": "612", "change_24h_pct": 0.8},
        {"symbol": "USDC", "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "chain": "ethereum", "price_usd": "1.00", "change_24h_pct": 0.01},
    ]
    for t in tokens:
        lite = sentinel_lite()  # Will use real shield data when available
        t["sentinel_lite"] = lite
    return tokens


routes = web.RouteTableDef()


@routes.get("/api/v1/tokens/ticker")
async def ticker(request: web.Request) -> web.Response:
    if not settings.FEATURE_TOKENS_BAR:
        return web.json_response({"error": "tokens_bar_disabled"}, status=503)
    now = time.time()
    if _CACHE["data"] is None or now - _CACHE["ts"] > _CACHE_TTL:
        _CACHE["data"] = await _fetch_ticker()
        _CACHE["ts"] = now
    return web.json_response({"tokens": _CACHE["data"]})


def setup_tokens_bar_routes(app: web.Application) -> None:
    """Register tokens bar routes on *app*."""
    app.router.add_routes(routes)
