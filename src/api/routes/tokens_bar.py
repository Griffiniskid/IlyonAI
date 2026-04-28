"""Top-of-page tokens ticker.

Serves the 5-token price strip used across the app. Prices, 24h change,
and market cap come from CoinGecko (a shared singleton client). Falls
back to hardcoded snapshot values if CoinGecko is unreachable so the UI
never breaks.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aiohttp import web

from src.config import settings
from src.defi.sentinel_lite import sentinel_lite

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL = 60  # seconds — price updates at most once per minute


# CoinGecko IDs for the five displayed tokens. Order here drives display order.
_TICKER_ROWS: list[dict[str, Any]] = [
    {"symbol": "BTC", "cg_id": "bitcoin",
     "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "chain": "ethereum"},
    {"symbol": "ETH", "cg_id": "ethereum",
     "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "chain": "ethereum"},
    {"symbol": "SOL", "cg_id": "solana",
     "address": "So11111111111111111111111111111111111111112", "chain": "solana"},
    {"symbol": "BNB", "cg_id": "binancecoin",
     "address": "0xB8c77482e45F1F44dE1745F52C74426C631bDD52", "chain": "bsc"},
    {"symbol": "USDC", "cg_id": "usd-coin",
     "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "chain": "ethereum"},
]

# Fallback snapshot so the UI never shows an error if CoinGecko is rate-limited.
_FALLBACK: dict[str, dict[str, Any]] = {
    "BTC": {"price_usd": "67500", "change_24h_pct": 0.0},
    "ETH": {"price_usd": "2300", "change_24h_pct": 0.0},
    "SOL": {"price_usd": "86", "change_24h_pct": 0.0},
    "BNB": {"price_usd": "620", "change_24h_pct": 0.0},
    "USDC": {"price_usd": "1.00", "change_24h_pct": 0.0},
}


async def _fetch_ticker() -> list[dict[str, Any]]:
    """Fetch live prices from CoinGecko; fall back to snapshot on failure."""
    prices: dict[str, dict[str, Any]] = {}
    try:
        from src.agent.services import get_agent_services

        services = await get_agent_services()
        price_client = services.price
        if price_client is not None:
            ids = [row["cg_id"] for row in _TICKER_ROWS]
            data = await price_client.get_token_price(ids, vs_currencies="usd")
            if isinstance(data, dict):
                for row in _TICKER_ROWS:
                    got = data.get(row["cg_id"])
                    if isinstance(got, dict) and got.get("usd") is not None:
                        prices[row["symbol"]] = {
                            "price_usd": str(got["usd"]),
                            "change_24h_pct": got.get("usd_24h_change", 0.0) or 0.0,
                            "market_cap": got.get("usd_market_cap", 0.0) or 0.0,
                        }
    except Exception as exc:
        logger.warning("tokens ticker fetch failed: %s", exc)

    rows: list[dict[str, Any]] = []
    for r in _TICKER_ROWS:
        sym = r["symbol"]
        snapshot = prices.get(sym) or _FALLBACK[sym]
        rows.append({
            "symbol": sym,
            "address": r["address"],
            "chain": r["chain"],
            "price_usd": snapshot["price_usd"],
            "change_24h_pct": snapshot.get("change_24h_pct", 0.0),
            "market_cap": snapshot.get("market_cap", 0.0),
            "sentinel_lite": sentinel_lite(),
        })
    return rows


routes = web.RouteTableDef()


@routes.get("/api/v1/tokens/ticker")
async def ticker(request: web.Request) -> web.Response:
    if not settings.FEATURE_TOKENS_BAR:
        return web.json_response({"error": "tokens_bar_disabled"}, status=503)
    now = time.time()
    if _CACHE["data"] is None or now - _CACHE["ts"] > _CACHE_TTL:
        _CACHE["data"] = await _fetch_ticker()
        _CACHE["ts"] = now
    return web.json_response({"tokens": _CACHE["data"], "updated_at": _CACHE["ts"]})


def setup_tokens_bar_routes(app: web.Application) -> None:
    """Register tokens bar routes on *app*."""
    app.router.add_routes(routes)
