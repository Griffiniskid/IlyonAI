"""
Whale tracker API routes.

Provides endpoints for tracking large transactions and whale wallet activity.
"""

import logging
from aiohttp import web
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio

from src.data.solana import SolanaClient
from src.data.dexscreener import DexScreenerClient
from src.api.schemas.responses import (
    WhaleActivityResponse, WhaleTransactionResponse, WhaleProfileResponse,
    ErrorResponse
)
from src.config import settings

logger = logging.getLogger(__name__)

# Cache for whale transactions
_whale_cache: Dict[str, any] = {}
_cache_ttl = 60  # seconds

# Known whale labels
KNOWN_WHALES = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": "Alameda",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Jump Trading",
    # Add more known whales as needed
}


async def get_recent_whale_txs(
    min_amount_usd: float = 10000,
    token_address: Optional[str] = None,
    limit: int = 50
) -> List[Dict]:
    """Fetch recent whale transactions from Helius/Solana"""
    # This would use Helius or another indexer in production
    # For now, return simulated data structure

    # In production, you would:
    # 1. Use Helius getSignaturesForAddress with amount filter
    # 2. Parse transaction details
    # 3. Get token prices from DexScreener

    return []


async def get_whale_activity(request: web.Request) -> web.Response:
    """
    GET /api/v1/whales

    Get recent whale transactions on Solana.

    Query params:
        - min_amount_usd: Minimum transaction value (default 10000)
        - token: Filter by token address
        - type: Filter by "buy" or "sell"
        - limit: Max transactions (default 50, max 200)
    """
    global _whale_cache

    min_amount = float(request.query.get('min_amount_usd', 10000))
    token_filter = request.query.get('token')
    type_filter = request.query.get('type')
    limit = min(int(request.query.get('limit', 50)), 200)

    cache_key = f"whales:{min_amount}:{token_filter}:{type_filter}:{limit}"

    # Check cache
    if cache_key in _whale_cache:
        cached = _whale_cache[cache_key]
        if (datetime.utcnow() - cached['time']).seconds < _cache_ttl:
            return web.json_response(cached['data'])

    try:
        # Fetch from DexScreener for recent large trades
        async with DexScreenerClient() as client:
            if token_filter:
                # Get trades for specific token
                pair_data = await client.get_token(token_filter)
                trades = []

                if pair_data and pair_data.get('main'):
                    # Extract recent trades from pair data
                    # DexScreener doesn't provide individual trades via API
                    # Would need Helius or Birdeye for this
                    pass
            else:
                # Get trending tokens and simulate whale activity
                trending = await client.get_trending_tokens(limit=20)
                trades = []

                # For demo: Create whale transactions from trending data
                for t in trending[:limit]:
                    base = t.get('baseToken', {})
                    vol = t.get('volume', {}).get('h1', 0)

                    if vol and float(vol) > min_amount:
                        trades.append(WhaleTransactionResponse(
                            signature="demo_" + base.get('address', '')[:16],
                            wallet_address="whale_wallet_demo",
                            wallet_label="Unknown Whale",
                            token_address=base.get('address', ''),
                            token_symbol=base.get('symbol', '???'),
                            token_name=base.get('name', 'Unknown'),
                            type="buy",
                            amount_tokens=float(vol) / max(float(t.get('priceUsd', 1)), 0.0001),
                            amount_usd=float(vol),
                            price_usd=float(t.get('priceUsd', 0)),
                            timestamp=datetime.utcnow() - timedelta(minutes=5),
                            dex_name=t.get('dexId', 'raydium').title()
                        ))

        # Filter by type if specified
        if type_filter:
            trades = [t for t in trades if t['type'] == type_filter]

        response = WhaleActivityResponse(
            transactions=trades[:limit],
            updated_at=datetime.utcnow(),
            filter_token=token_filter,
            min_amount_usd=min_amount
        ).model_dump(mode='json')

        # Cache
        _whale_cache[cache_key] = {
            'data': response,
            'time': datetime.utcnow()
        }

        return web.json_response(response)

    except Exception as e:
        logger.error(f"Whale activity error: {e}", exc_info=True)
        return web.json_response(
            ErrorResponse(
                error="Failed to fetch whale activity",
                code="WHALE_FAILED",
                details={"message": str(e)}
            ).model_dump(mode='json'),
            status=500
        )


async def get_whale_activity_for_token(request: web.Request) -> web.Response:
    """
    GET /api/v1/whales/token/{address}

    Get whale activity for a specific token.
    """
    token_address = request.match_info.get('address')

    if not token_address:
        return web.json_response(
            ErrorResponse(error="Token address required", code="MISSING_ADDRESS").model_dump(mode='json'),
            status=400
        )

    min_amount = float(request.query.get('min_amount_usd', 5000))
    limit = min(int(request.query.get('limit', 50)), 200)

    try:
        async with DexScreenerClient() as client:
            pair_data = await client.get_token(token_address)

        trades = []

        if pair_data and pair_data.get('main'):
            p = pair_data['main']
            base = p.get('baseToken', {})

            # Simulate recent whale trades based on volume
            vol_1h = float(p.get('volume', {}).get('h1', 0) or 0)

            if vol_1h > min_amount:
                # Create demo whale transactions
                trades.append(WhaleTransactionResponse(
                    signature="demo_" + token_address[:16],
                    wallet_address="whale_wallet",
                    wallet_label=None,
                    token_address=token_address,
                    token_symbol=base.get('symbol', '???'),
                    token_name=base.get('name', 'Unknown'),
                    type="buy",
                    amount_tokens=vol_1h / max(float(p.get('priceUsd', 1)), 0.0001),
                    amount_usd=vol_1h,
                    price_usd=float(p.get('priceUsd', 0)),
                    timestamp=datetime.utcnow() - timedelta(minutes=10),
                    dex_name=p.get('dexId', 'raydium').title()
                ))

        response = WhaleActivityResponse(
            transactions=trades,
            updated_at=datetime.utcnow(),
            filter_token=token_address,
            min_amount_usd=min_amount
        ).model_dump(mode='json')

        return web.json_response(response)

    except Exception as e:
        logger.error(f"Whale activity for token error: {e}")
        return web.json_response(
            ErrorResponse(error="Failed to fetch whale activity", code="WHALE_FAILED").model_dump(mode='json'),
            status=500
        )


async def get_whale_profile(request: web.Request) -> web.Response:
    """
    GET /api/v1/whales/wallet/{address}

    Get profile and activity for a whale wallet.
    """
    wallet_address = request.match_info.get('address')

    if not wallet_address:
        return web.json_response(
            ErrorResponse(error="Wallet address required", code="MISSING_ADDRESS").model_dump(mode='json'),
            status=400
        )

    try:
        # Get label if known
        label = KNOWN_WHALES.get(wallet_address)

        # In production, would fetch from Helius/indexer
        # For now, return basic profile

        profile = WhaleProfileResponse(
            address=wallet_address,
            label=label,
            total_volume_usd=0,
            transaction_count=0,
            tokens_traded=0,
            win_rate=None,
            avg_holding_time=None,
            recent_transactions=[]
        ).model_dump(mode='json')

        return web.json_response(profile)

    except Exception as e:
        logger.error(f"Whale profile error: {e}")
        return web.json_response(
            ErrorResponse(error="Failed to fetch whale profile", code="PROFILE_FAILED").model_dump(mode='json'),
            status=500
        )


def setup_whale_routes(app: web.Application):
    """Setup whale tracker API routes"""
    app.router.add_get('/api/v1/whales', get_whale_activity)
    app.router.add_get('/api/v1/whales/token/{address}', get_whale_activity_for_token)
    app.router.add_get('/api/v1/whales/wallet/{address}', get_whale_profile)

    logger.info("Whale routes registered")
