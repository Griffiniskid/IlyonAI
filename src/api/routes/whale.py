"""
Whale tracker API routes.

Provides endpoints for tracking large transactions and whale wallet activity.
Uses Helius API for real transaction data when available.
"""

import logging
from aiohttp import web
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
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
_whale_cache: Dict[str, Any] = {}
_cache_ttl = 300  # 5 minutes (no auto-refresh, manual search only)

# Known whale labels
KNOWN_WHALES = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": "Alameda",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Jump Trading",
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "Wintermute",
    "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm": "Circle",
    # Add more known whales as needed
}


async def get_whale_activity(request: web.Request) -> web.Response:
    """
    GET /api/v1/whales

    Get recent whale transactions on Solana using real on-chain data.

    Query params:
        - min_amount_usd: Minimum transaction value (default 10000)
        - token: Filter by token address
        - type: Filter by "buy" or "sell"
        - limit: Max transactions (default 50, max 200)
    """
    global _whale_cache

    min_amount = float(request.query.get('min_amount_usd', 1000))
    token_filter = request.query.get('token')
    type_filter = request.query.get('type')
    limit = min(int(request.query.get('limit', 50)), 200)
    force_refresh = request.query.get('force_refresh', '').lower() in ('1', 'true')

    cache_key = f"whales:{min_amount}:{token_filter}:{type_filter}:{limit}"

    # Check cache (skip if force_refresh)
    if not force_refresh and cache_key in _whale_cache:
        cached = _whale_cache[cache_key]
        if (datetime.utcnow() - cached['time']).seconds < _cache_ttl:
            return web.json_response(cached['data'])

    try:
        # Initialize Solana client with Helius for whale tracking
        solana = SolanaClient(
            rpc_url=settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key
        )
        
        try:
            if token_filter:
                # Get whale transactions for specific token
                raw_transactions = await solana.get_token_whale_transactions(
                    token_address=token_filter,
                    min_amount_usd=min_amount,
                    limit=limit
                )
            else:
                # Get general whale activity
                raw_transactions = await solana.get_recent_large_transactions(
                    min_amount_usd=min_amount,
                    limit=limit
                )
        finally:
            await solana.close()
        
        # Convert to response format
        trades = []
        for tx in raw_transactions:
            try:
                # Check known whale labels
                wallet_addr = tx.get('wallet_address', '')
                wallet_label = tx.get('wallet_label') or KNOWN_WHALES.get(wallet_addr)
                
                # Parse timestamp
                ts = tx.get('timestamp')
                if isinstance(ts, str):
                    try:
                        timestamp = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    except:
                        timestamp = datetime.utcnow()
                elif isinstance(ts, datetime):
                    timestamp = ts
                else:
                    timestamp = datetime.utcnow()
                
                trades.append(WhaleTransactionResponse(
                    signature=tx.get('signature', ''),
                    wallet_address=wallet_addr,
                    wallet_label=wallet_label,
                    token_address=tx.get('token_address', ''),
                    token_symbol=tx.get('token_symbol', '???'),
                    token_name=tx.get('token_name', 'Unknown'),
                    type=tx.get('type', 'buy'),
                    amount_tokens=float(tx.get('amount_tokens', 0)),
                    amount_usd=float(tx.get('amount_usd', 0)),
                    price_usd=float(tx.get('price_usd', 0)),
                    timestamp=timestamp,
                    dex_name=tx.get('dex_name', 'Unknown')
                ))
            except Exception as e:
                logger.debug(f"Error converting whale tx: {e}")
                continue

        # Filter by type if specified
        if type_filter:
            trades = [t for t in trades if t.type == type_filter]

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

    Get whale activity for a specific token using real on-chain data.
    """
    token_address = request.match_info.get('address')

    if not token_address:
        return web.json_response(
            ErrorResponse(error="Token address required", code="MISSING_ADDRESS").model_dump(mode='json'),
            status=400
        )

    min_amount = float(request.query.get('min_amount_usd', 1000))
    limit = min(int(request.query.get('limit', 50)), 200)

    try:
        # Step 1: Get token metadata first so we don't have "???" symbols
        symbol = "???"
        name = "Unknown"
        
        try:
            async with DexScreenerClient() as client:
                token_data = await client.get_token(token_address)
                if token_data and token_data.get('main'):
                    base = token_data['main'].get('baseToken', {})
                    symbol = base.get('symbol', symbol)
                    name = base.get('name', name)
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for whale check: {e}")

        # Step 2: Initialize Solana client with Helius
        solana = SolanaClient(
            rpc_url=settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key
        )
        
        try:
            raw_transactions = await solana.get_token_whale_transactions(
                token_address=token_address,
                min_amount_usd=min_amount,
                limit=limit,
                token_symbol=symbol,
                token_name=name
            )
        finally:
            await solana.close()
        
        # Convert to response format
        trades = []
        for tx in raw_transactions:
            try:
                wallet_addr = tx.get('wallet_address', '')
                wallet_label = tx.get('wallet_label') or KNOWN_WHALES.get(wallet_addr)
                
                # Parse timestamp
                ts = tx.get('timestamp')
                if isinstance(ts, str):
                    try:
                        timestamp = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    except:
                        timestamp = datetime.utcnow()
                elif isinstance(ts, datetime):
                    timestamp = ts
                else:
                    timestamp = datetime.utcnow()
                
                trades.append(WhaleTransactionResponse(
                    signature=tx.get('signature', ''),
                    wallet_address=wallet_addr,
                    wallet_label=wallet_label,
                    token_address=tx.get('token_address', token_address),
                    token_symbol=tx.get('token_symbol', symbol),
                    token_name=tx.get('token_name', name),
                    type=tx.get('type', 'buy'),
                    amount_tokens=float(tx.get('amount_tokens', 0)),
                    amount_usd=float(tx.get('amount_usd', 0)),
                    price_usd=float(tx.get('price_usd', 0)),
                    timestamp=timestamp,
                    dex_name=tx.get('dex_name', 'Unknown')
                ))
            except Exception as e:
                logger.debug(f"Error converting whale tx: {e}")
                continue

        # If no transactions from Helius, fallback to volume-based estimation is REMOVED
        # We only want real data now.

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
