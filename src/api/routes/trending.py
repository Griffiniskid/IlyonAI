"""
Trending tokens API routes.

Provides endpoints for fetching trending, new, and top gaining/losing tokens
across all supported chains.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from aiohttp import web

from src.api.schemas.responses import ErrorResponse, TrendingResponse, TrendingTokenResponse
from src.data.dexscreener import DexScreenerClient

logger = logging.getLogger(__name__)

_trending_cache: Dict[str, Any] = {}
_cache_ttl = 30
SUPPORTED_CHAINS = {"solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"}
CHAIN_ALIASES = {"eth": "ethereum", "arb": "arbitrum", "bnb": "bsc", "matic": "polygon", "op": "optimism", "avax": "avalanche", "sol": "solana"}


def _parse_chain(chain: Optional[str]) -> Optional[str]:
    if not chain:
        return None
    normalized = chain.strip().lower()
    normalized = CHAIN_ALIASES.get(normalized, normalized)
    return normalized if normalized in SUPPORTED_CHAINS else None


def _pair_to_response(pair: Dict[str, Any]) -> Optional[TrendingTokenResponse]:
    try:
        base_token = pair.get("baseToken", {})
        liquidity = pair.get("liquidity", {})
        price_change = pair.get("priceChange", {})
        volume = pair.get("volume", {})
        info = pair.get("info", {})
        chain = str(pair.get("chainId") or "unknown").lower()

        created_at = pair.get("pairCreatedAt", 0)
        age_hours = 0.0
        if created_at:
            age_hours = (datetime.now().timestamp() - created_at / 1000) / 3600

        txns = pair.get("txns", {}).get("h1", {})
        txns_1h = int(txns.get("buys", 0) or 0) + int(txns.get("sells", 0) or 0)

        return TrendingTokenResponse(
            address=base_token.get("address", ""),
            chain=chain,
            name=base_token.get("name", "Unknown"),
            symbol=base_token.get("symbol", "???"),
            logo_url=info.get("imageUrl"),
            price_usd=float(pair.get("priceUsd", 0) or 0),
            price_change_24h=float(price_change.get("h24", 0) or 0),
            price_change_1h=float(price_change.get("h1", 0) or 0),
            volume_24h=float(volume.get("h24", 0) or 0),
            liquidity_usd=float(liquidity.get("usd", 0) or 0),
            market_cap=float(pair.get("marketCap", 0) or 0),
            age_hours=age_hours,
            dex_name=str(pair.get("dexId", "unknown")).title(),
            pair_address=pair.get("pairAddress"),
            txns_1h=txns_1h,
        )
    except Exception as e:
        logger.warning(f"Error parsing trending token pair: {e}")
        return None


async def _fetch_category_tokens(category: str, limit: int, chain: Optional[str]) -> List[Dict[str, Any]]:
    async with DexScreenerClient() as client:
        if category == "gainers":
            return await client.get_top_gainers(limit=limit, chain=chain)
        if category == "losers":
            return await client.get_top_losers(limit=limit, chain=chain)
        if category == "new":
            return await client.get_new_tokens(limit=limit, chain=chain)
        return await client.get_trending_tokens(limit=limit, chain=chain)


async def _build_trending_response(category: str, limit: int, chain: Optional[str], force_refresh: bool) -> Dict[str, Any]:
    cache_key = f"{category}:{chain or 'all'}:{limit}"
    effective_ttl = 10 if category == "new" else _cache_ttl

    if not force_refresh and cache_key in _trending_cache:
        cached = _trending_cache[cache_key]
        if (datetime.utcnow() - cached["time"]).seconds < effective_ttl:
            return cached["data"]

    raw_tokens = await _fetch_category_tokens(category=category, limit=limit, chain=chain)
    tokens = []
    for pair in raw_tokens:
        token = _pair_to_response(pair)
        if token:
            tokens.append(token)

    response = TrendingResponse(
        tokens=tokens,
        updated_at=datetime.utcnow(),
        category=category,
        filter_chain=chain,
    ).model_dump(mode="json")

    _trending_cache[cache_key] = {"data": response, "time": datetime.utcnow()}
    return response


async def get_trending_tokens(request: web.Request) -> web.Response:
    """
    GET /api/v1/trending

    Query params:
        - limit: Max tokens to return (default 20, max 50)
        - category: trending | gainers | losers | new
        - chain: Optional chain filter across supported chains
    """
    try:
        limit = min(int(request.query.get("limit", 20)), 50)
    except ValueError:
        limit = 20

    category = request.query.get("category", "trending").lower()
    if category not in {"trending", "gainers", "losers", "new"}:
        category = "trending"

    raw_chain = request.query.get("chain")
    chain = _parse_chain(raw_chain)
    if raw_chain and chain is None:
        return web.json_response(
            ErrorResponse(
                error="Unsupported chain filter",
                code="INVALID_CHAIN",
                details={"supported": sorted(SUPPORTED_CHAINS)},
            ).model_dump(mode="json"),
            status=400,
        )

    force_refresh = request.query.get("force_refresh", "").lower() in ("1", "true")

    try:
        response = await _build_trending_response(
            category=category,
            limit=limit,
            chain=chain,
            force_refresh=force_refresh,
        )
        return web.json_response(response)
    except Exception as e:
        logger.error(f"Trending endpoint error: {e}", exc_info=True)
        return web.json_response(
            ErrorResponse(
                error="Failed to fetch trending tokens",
                code="TRENDING_FAILED",
                details={"message": str(e)},
            ).model_dump(mode="json"),
            status=500,
        )


async def get_new_pairs(request: web.Request) -> web.Response:
    query = dict(request.rel_url.query)
    query["category"] = "new"
    request = request.clone(rel_url=request.rel_url.with_query(query))
    return await get_trending_tokens(request)


async def get_gainers(request: web.Request) -> web.Response:
    query = dict(request.rel_url.query)
    query["category"] = "gainers"
    request = request.clone(rel_url=request.rel_url.with_query(query))
    return await get_trending_tokens(request)


async def get_losers(request: web.Request) -> web.Response:
    query = dict(request.rel_url.query)
    query["category"] = "losers"
    request = request.clone(rel_url=request.rel_url.with_query(query))
    return await get_trending_tokens(request)


def setup_trending_routes(app: web.Application):
    """Setup trending API routes."""
    app.router.add_get("/api/v1/trending", get_trending_tokens)
    app.router.add_get("/api/v1/trending/new", get_new_pairs)
    app.router.add_get("/api/v1/trending/gainers", get_gainers)
    app.router.add_get("/api/v1/trending/losers", get_losers)

    logger.info("Trending routes registered")
