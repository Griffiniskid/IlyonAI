"""
Trending tokens API routes.

Provides endpoints for fetching trending, new, and top gaining/losing tokens.
"""

import logging
from aiohttp import web
from datetime import datetime
from typing import List, Dict, Any

from src.data.dexscreener import DexScreenerClient
from src.api.schemas.responses import TrendingTokenResponse, TrendingResponse, ErrorResponse

logger = logging.getLogger(__name__)

# Cache for trending data (simple in-memory with TTL)
_trending_cache: Dict[str, Any] = {}
_cache_ttl = 30  # seconds


async def get_trending_tokens(request: web.Request) -> web.Response:
    """
    GET /api/v1/trending

    Get trending tokens on Solana from DexScreener.

    Query params:
        - limit: Max tokens to return (default 20, max 50)
        - category: "trending" | "gainers" | "losers" | "new" (default "trending")
    """
    global _trending_cache

    limit = min(int(request.query.get('limit', 20)), 50)
    category = request.query.get('category', 'trending')
    force_refresh = request.query.get('force_refresh', '').lower() in ('1', 'true')

    cache_key = f"{category}:{limit}"
    # Shorter cache for new pairs to enable near-real-time updates
    effective_ttl = 10 if category == 'new' else _cache_ttl

    # Check cache (skip if force_refresh)
    if not force_refresh and cache_key in _trending_cache:
        cached = _trending_cache[cache_key]
        if (datetime.utcnow() - cached['time']).seconds < effective_ttl:
            return web.json_response(cached['data'])

    try:
        async with DexScreenerClient() as client:
            if category == 'trending':
                raw_tokens = await client.get_trending_tokens(limit=limit)
            elif category == 'gainers':
                raw_tokens = await client.get_top_gainers(limit=limit)
            elif category == 'losers':
                raw_tokens = await client.get_top_losers(limit=limit)
            elif category == 'new':
                raw_tokens = await client.get_new_tokens(limit=limit)
            else:
                raw_tokens = await client.get_trending_tokens(limit=limit)

        # Convert to response format
        tokens = []
        for t in raw_tokens:
            try:
                base_token = t.get('baseToken', {})
                liquidity = t.get('liquidity', {})
                price_change = t.get('priceChange', {})
                volume = t.get('volume', {})
                info = t.get('info', {})

                # Calculate age
                created_at = t.get('pairCreatedAt', 0)
                age_hours = 0
                if created_at:
                    age_hours = (datetime.now().timestamp() - created_at / 1000) / 3600

                txns = t.get('txns', {}).get('h1', {})
                txns_1h = int(txns.get('buys', 0) or 0) + int(txns.get('sells', 0) or 0)

                tokens.append(TrendingTokenResponse(
                    address=base_token.get('address', ''),
                    name=base_token.get('name', 'Unknown'),
                    symbol=base_token.get('symbol', '???'),
                    logo_url=info.get('imageUrl'),
                    price_usd=float(t.get('priceUsd', 0) or 0),
                    price_change_24h=float(price_change.get('h24', 0) or 0),
                    price_change_1h=float(price_change.get('h1', 0) or 0),
                    volume_24h=float(volume.get('h24', 0) or 0),
                    liquidity_usd=float(liquidity.get('usd', 0) or 0),
                    market_cap=float(t.get('marketCap', 0) or 0),
                    age_hours=age_hours,
                    dex_name=t.get('dexId', 'unknown').title(),
                    txns_1h=txns_1h,
                ))
            except Exception as e:
                logger.warning(f"Error parsing token: {e}")
                continue

        response = TrendingResponse(
            tokens=tokens,
            updated_at=datetime.utcnow(),
            category=category
        ).model_dump(mode='json')

        # Cache response
        _trending_cache[cache_key] = {
            'data': response,
            'time': datetime.utcnow()
        }

        return web.json_response(response)

    except Exception as e:
        logger.error(f"Trending endpoint error: {e}", exc_info=True)
        return web.json_response(
            ErrorResponse(
                error="Failed to fetch trending tokens",
                code="TRENDING_FAILED",
                details={"message": str(e)}
            ).model_dump(mode='json'),
            status=500
        )


async def get_new_pairs(request: web.Request) -> web.Response:
    """
    GET /api/v1/trending/new

    Get newly created token pairs on Solana.
    """
    request.query['category'] = 'new'
    return await get_trending_tokens(request)


async def get_gainers(request: web.Request) -> web.Response:
    """
    GET /api/v1/trending/gainers

    Get top gaining tokens on Solana.
    """
    limit = min(int(request.query.get('limit', 20)), 50)

    try:
        async with DexScreenerClient() as client:
            raw_tokens = await client.get_top_gainers(limit=limit)

        tokens = []
        for t in raw_tokens:
            try:
                base_token = t.get('baseToken', {})
                liquidity = t.get('liquidity', {})
                price_change = t.get('priceChange', {})
                volume = t.get('volume', {})
                info = t.get('info', {})

                created_at = t.get('pairCreatedAt', 0)
                age_hours = 0
                if created_at:
                    age_hours = (datetime.now().timestamp() - created_at / 1000) / 3600

                txns = t.get('txns', {}).get('h1', {})
                txns_1h = int(txns.get('buys', 0) or 0) + int(txns.get('sells', 0) or 0)

                tokens.append(TrendingTokenResponse(
                    address=base_token.get('address', ''),
                    name=base_token.get('name', 'Unknown'),
                    symbol=base_token.get('symbol', '???'),
                    logo_url=info.get('imageUrl'),
                    price_usd=float(t.get('priceUsd', 0) or 0),
                    price_change_24h=float(price_change.get('h24', 0) or 0),
                    price_change_1h=float(price_change.get('h1', 0) or 0),
                    volume_24h=float(volume.get('h24', 0) or 0),
                    liquidity_usd=float(liquidity.get('usd', 0) or 0),
                    market_cap=float(t.get('marketCap', 0) or 0),
                    age_hours=age_hours,
                    dex_name=t.get('dexId', 'unknown').title(),
                    txns_1h=txns_1h,
                ))
            except Exception:
                continue

        response = TrendingResponse(
            tokens=tokens,
            updated_at=datetime.utcnow(),
            category='gainers'
        ).model_dump(mode='json')

        return web.json_response(response)

    except Exception as e:
        logger.error(f"Gainers endpoint error: {e}")
        return web.json_response(
            ErrorResponse(error="Failed to fetch gainers", code="GAINERS_FAILED").model_dump(mode='json'),
            status=500
        )


async def get_losers(request: web.Request) -> web.Response:
    """
    GET /api/v1/trending/losers

    Get top losing tokens on Solana.
    """
    limit = min(int(request.query.get('limit', 20)), 50)

    try:
        async with DexScreenerClient() as client:
            raw_tokens = await client.get_top_losers(limit=limit)

        tokens = []
        for t in raw_tokens:
            try:
                base_token = t.get('baseToken', {})
                liquidity = t.get('liquidity', {})
                price_change = t.get('priceChange', {})
                volume = t.get('volume', {})
                info = t.get('info', {})

                created_at = t.get('pairCreatedAt', 0)
                age_hours = 0
                if created_at:
                    age_hours = (datetime.now().timestamp() - created_at / 1000) / 3600

                txns = t.get('txns', {}).get('h1', {})
                txns_1h = int(txns.get('buys', 0) or 0) + int(txns.get('sells', 0) or 0)

                tokens.append(TrendingTokenResponse(
                    address=base_token.get('address', ''),
                    name=base_token.get('name', 'Unknown'),
                    symbol=base_token.get('symbol', '???'),
                    logo_url=info.get('imageUrl'),
                    price_usd=float(t.get('priceUsd', 0) or 0),
                    price_change_24h=float(price_change.get('h24', 0) or 0),
                    price_change_1h=float(price_change.get('h1', 0) or 0),
                    volume_24h=float(volume.get('h24', 0) or 0),
                    liquidity_usd=float(liquidity.get('usd', 0) or 0),
                    market_cap=float(t.get('marketCap', 0) or 0),
                    age_hours=age_hours,
                    dex_name=t.get('dexId', 'unknown').title(),
                    txns_1h=txns_1h,
                ))
            except Exception:
                continue

        response = TrendingResponse(
            tokens=tokens,
            updated_at=datetime.utcnow(),
            category='losers'
        ).model_dump(mode='json')

        return web.json_response(response)

    except Exception as e:
        logger.error(f"Losers endpoint error: {e}")
        return web.json_response(
            ErrorResponse(error="Failed to fetch losers", code="LOSERS_FAILED").model_dump(mode='json'),
            status=500
        )


def setup_trending_routes(app: web.Application):
    """Setup trending API routes"""
    app.router.add_get('/api/v1/trending', get_trending_tokens)
    app.router.add_get('/api/v1/trending/new', get_new_pairs)
    app.router.add_get('/api/v1/trending/gainers', get_gainers)
    app.router.add_get('/api/v1/trending/losers', get_losers)

    logger.info("Trending routes registered")
