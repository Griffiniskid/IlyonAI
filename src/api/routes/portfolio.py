"""
Portfolio tracking API routes.

Provides endpoints for tracking wallet holdings and portfolio analytics.
"""

import logging
from aiohttp import web
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from src.data.solana import SolanaClient
from src.data.dexscreener import DexScreenerClient
from src.api.schemas.responses import (
    PortfolioResponse, PortfolioTokenResponse,
    TrackedWalletsResponse, TrackedWalletResponse,
    ErrorResponse
)
from src.api.schemas.requests import TrackWalletRequest
from src.config import settings

logger = logging.getLogger(__name__)

# In-memory storage for demo (replace with database in production)
_tracked_wallets: Dict[str, Dict[str, any]] = {}  # user_id -> {wallets: [...]}


def get_user_id(request: web.Request) -> Optional[str]:
    """Extract user ID from session/auth"""
    # Get from auth middleware
    return request.get('user_id') or request.headers.get('X-User-Id')


async def get_wallet_tokens(wallet_address: str) -> List[Dict]:
    """Fetch token holdings for a wallet"""
    try:
        solana = SolanaClient(
            settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key
        )

        # Get token accounts
        tokens = await solana.get_wallet_tokens(wallet_address)
        await solana.close()

        return tokens
    except Exception as e:
        logger.error(f"Error fetching wallet tokens: {e}")
        return []


async def get_portfolio(request: web.Request) -> web.Response:
    """
    GET /api/v1/portfolio

    Get aggregated portfolio for all tracked wallets.
    Requires authentication.
    """
    user_id = get_user_id(request)

    if not user_id:
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    # Get tracked wallets for user
    user_data = _tracked_wallets.get(user_id, {'wallets': []})
    wallets = user_data.get('wallets', [])

    if not wallets:
        return web.json_response(
            PortfolioResponse(
                wallet_address="aggregate",
                total_value_usd=0,
                total_pnl_usd=0,
                total_pnl_percent=0,
                tokens=[],
                health_score=50,
                last_updated=datetime.utcnow()
            ).model_dump(mode='json')
        )

    # Aggregate tokens from all wallets
    all_tokens = []
    total_value = 0

    for wallet in wallets:
        tokens = await get_wallet_tokens(wallet['address'])

        for token in tokens:
            # Add to aggregated list
            all_tokens.append(PortfolioTokenResponse(
                address=token.get('mint', ''),
                name=token.get('name', 'Unknown'),
                symbol=token.get('symbol', '???'),
                logo_url=token.get('logo'),
                balance=token.get('amount', 0),
                balance_usd=token.get('value_usd', 0),
                price_usd=token.get('price_usd', 0),
                price_change_24h=token.get('price_change_24h', 0),
                safety_score=None,  # Would need to run analysis
                risk_level="UNKNOWN"
            ))
            total_value += token.get('value_usd', 0)

    # Calculate health score based on token risk (placeholder)
    health_score = 70  # Default moderate score

    response = PortfolioResponse(
        wallet_address="aggregate",
        total_value_usd=total_value,
        total_pnl_usd=0,  # Would need historical data
        total_pnl_percent=0,
        tokens=all_tokens,
        health_score=health_score,
        last_updated=datetime.utcnow()
    ).model_dump(mode='json')

    return web.json_response(response)


async def get_wallet_portfolio(request: web.Request) -> web.Response:
    """
    GET /api/v1/portfolio/{wallet}

    Get portfolio for a specific wallet.
    """
    wallet_address = request.match_info.get('wallet')

    if not wallet_address:
        return web.json_response(
            ErrorResponse(error="Wallet address required", code="MISSING_WALLET").model_dump(mode='json'),
            status=400
        )

    # Validate address
    try:
        solana = SolanaClient(settings.solana_rpc_url)
        if not solana.is_valid_address(wallet_address):
            await solana.close()
            return web.json_response(
                ErrorResponse(error="Invalid wallet address", code="INVALID_ADDRESS").model_dump(mode='json'),
                status=400
            )
        await solana.close()
    except Exception:
        pass

    # Fetch tokens
    tokens_raw = await get_wallet_tokens(wallet_address)

    tokens = []
    total_value = 0

    for token in tokens_raw:
        value = token.get('value_usd', 0)
        tokens.append(PortfolioTokenResponse(
            address=token.get('mint', ''),
            name=token.get('name', 'Unknown'),
            symbol=token.get('symbol', '???'),
            logo_url=token.get('logo'),
            balance=token.get('amount', 0),
            balance_usd=value,
            price_usd=token.get('price_usd', 0),
            price_change_24h=token.get('price_change_24h', 0),
            safety_score=None,
            risk_level="UNKNOWN"
        ))
        total_value += value

    response = PortfolioResponse(
        wallet_address=wallet_address,
        total_value_usd=total_value,
        total_pnl_usd=0,
        total_pnl_percent=0,
        tokens=tokens,
        health_score=70,
        last_updated=datetime.utcnow()
    ).model_dump(mode='json')

    return web.json_response(response)


async def get_tracked_wallets(request: web.Request) -> web.Response:
    """
    GET /api/v1/portfolio/wallets

    Get list of tracked wallets for the user.
    Requires authentication.
    """
    user_id = get_user_id(request)

    if not user_id:
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    user_data = _tracked_wallets.get(user_id, {'wallets': []})
    wallets = user_data.get('wallets', [])

    tracked = [
        TrackedWalletResponse(
            address=w['address'],
            label=w.get('label'),
            added_at=w['added_at'],
            last_synced=w.get('last_synced'),
            token_count=w.get('token_count', 0),
            total_value_usd=w.get('total_value_usd', 0)
        )
        for w in wallets
    ]

    return web.json_response(
        TrackedWalletsResponse(wallets=tracked).model_dump(mode='json')
    )


async def track_wallet(request: web.Request) -> web.Response:
    """
    POST /api/v1/portfolio/wallets

    Add a wallet to tracking.
    Requires authentication.
    """
    user_id = get_user_id(request)

    if not user_id:
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    try:
        data = await request.json()
        req = TrackWalletRequest(**data)
    except Exception as e:
        return web.json_response(
            ErrorResponse(error="Invalid request", code="INVALID_REQUEST").model_dump(mode='json'),
            status=400
        )

    # Initialize user data if needed
    if user_id not in _tracked_wallets:
        _tracked_wallets[user_id] = {'wallets': []}

    # Check if already tracking
    existing = [w for w in _tracked_wallets[user_id]['wallets'] if w['address'] == req.address]
    if existing:
        return web.json_response(
            ErrorResponse(error="Wallet already tracked", code="ALREADY_TRACKED").model_dump(mode='json'),
            status=409
        )

    # Check limit
    if len(_tracked_wallets[user_id]['wallets']) >= 10:
        return web.json_response(
            ErrorResponse(error="Maximum 10 wallets allowed", code="LIMIT_REACHED").model_dump(mode='json'),
            status=400
        )

    # Add wallet
    wallet_data = {
        'address': req.address,
        'label': req.label,
        'added_at': datetime.utcnow(),
        'last_synced': None,
        'token_count': 0,
        'total_value_usd': 0
    }

    _tracked_wallets[user_id]['wallets'].append(wallet_data)

    return web.json_response(
        TrackedWalletResponse(**wallet_data).model_dump(mode='json'),
        status=201
    )


async def untrack_wallet(request: web.Request) -> web.Response:
    """
    DELETE /api/v1/portfolio/wallets/{address}

    Remove a wallet from tracking.
    Requires authentication.
    """
    user_id = get_user_id(request)
    wallet_address = request.match_info.get('address')

    if not user_id:
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    if user_id not in _tracked_wallets:
        return web.json_response(
            ErrorResponse(error="Wallet not found", code="NOT_FOUND").model_dump(mode='json'),
            status=404
        )

    # Remove wallet
    wallets = _tracked_wallets[user_id]['wallets']
    _tracked_wallets[user_id]['wallets'] = [
        w for w in wallets if w['address'] != wallet_address
    ]

    if len(_tracked_wallets[user_id]['wallets']) == len(wallets):
        return web.json_response(
            ErrorResponse(error="Wallet not found", code="NOT_FOUND").model_dump(mode='json'),
            status=404
        )

    return web.Response(status=204)


def setup_portfolio_routes(app: web.Application):
    """Setup portfolio API routes"""
    app.router.add_get('/api/v1/portfolio', get_portfolio)
    app.router.add_get('/api/v1/portfolio/wallets', get_tracked_wallets)
    app.router.add_post('/api/v1/portfolio/wallets', track_wallet)
    app.router.add_delete('/api/v1/portfolio/wallets/{address}', untrack_wallet)
    app.router.add_get('/api/v1/portfolio/{wallet}', get_wallet_portfolio)

    logger.info("Portfolio routes registered")
