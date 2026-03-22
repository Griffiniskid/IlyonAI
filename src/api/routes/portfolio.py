"""
Portfolio tracking API routes.

Provides endpoints for tracking wallet holdings and portfolio analytics.
Uses proper authentication and database storage.
"""

import logging
from aiohttp import web
from datetime import datetime
from typing import Dict, List, Optional

from src.data.solana import SolanaClient
from src.data.moralis import MoralisClient
from src.api.response_envelope import make_envelope
from src.api.response_envelope import envelope_error_response, envelope_response
from src.portfolio.multichain_aggregator import MultiChainPortfolioAggregator
from src.api.schemas.responses import (
    PortfolioResponse, PortfolioTokenResponse,
    TrackedWalletsResponse, TrackedWalletResponse,
    ErrorResponse
)
from src.api.schemas.requests import TrackWalletRequest
from src.api.routes.auth import require_auth
from src.config import settings

logger = logging.getLogger(__name__)


def get_user_wallet(request: web.Request) -> Optional[str]:
    """Extract authenticated user wallet from request."""
    return request.get('user_wallet')


def _calculate_health_score(tokens: List, total_value: float) -> int:
    """
    Calculate portfolio health score (0-100) based on meaningful criteria.

    Factors:
    - Diversity: How spread out holdings are (Herfindahl index)
    - Stability: Average absolute 24h price change
    - Token count: More tokens = better diversification
    """
    if not tokens or total_value <= 0:
        return 50  # Default for empty portfolios

    score = 50  # Base score

    # 1. Diversity bonus (0-20 points) - Herfindahl index
    # Lower HHI = more diversified = higher score
    weights = []
    for token in tokens:
        val = getattr(token, 'balance_usd', 0) if hasattr(token, 'balance_usd') else token.get('balance_usd', 0)
        if total_value > 0 and val > 0:
            weights.append(val / total_value)

    if weights:
        hhi = sum(w ** 2 for w in weights)
        # HHI ranges from 1/n (perfectly diversified) to 1 (single token)
        # Map: HHI 1.0 -> 0 points, HHI < 0.1 -> 20 points
        diversity_score = max(0, min(20, int((1 - hhi) * 22)))
        score += diversity_score

    # 2. Stability bonus (0-15 points) - lower avg volatility = higher
    price_changes = []
    for token in tokens:
        change = getattr(token, 'price_change_24h', 0) if hasattr(token, 'price_change_24h') else token.get('price_change_24h', 0)
        if change is not None:
            price_changes.append(abs(float(change)))

    if price_changes:
        avg_volatility = sum(price_changes) / len(price_changes)
        # Low volatility (<10%) = 15 points, high (>100%) = 0 points
        stability_score = max(0, min(15, int(15 - avg_volatility / 7)))
        score += stability_score

    # 3. Token count bonus (0-15 points)
    n_tokens = len(tokens)
    if n_tokens >= 10:
        score += 15
    elif n_tokens >= 5:
        score += 10
    elif n_tokens >= 3:
        score += 5

    return max(0, min(100, score))


async def get_wallet_tokens(wallet_address: str) -> List[Dict]:
    """Fetch token holdings for a wallet using Helius (Solana) and Moralis (EVM)."""
    tokens = []
    
    # Check if wallet is EVM or Solana based on format
    is_evm = wallet_address.startswith("0x") and len(wallet_address) == 42
    
    if not is_evm:
        # Solana handling
        try:
            solana = SolanaClient(
                settings.solana_rpc_url,
                helius_api_key=settings.helius_api_key
            )
            sol_tokens = await solana.get_wallet_assets(wallet_address)
            await solana.close()
            tokens.extend(sol_tokens)
        except Exception as e:
            logger.error(f"Error fetching Solana wallet tokens: {e}")
    else:
        # EVM handling
        try:
            from src.data.moralis import MoralisClient
            moralis = MoralisClient()
            import asyncio
            
            # Fetch balances for top EVM chains
            evm_chains = ["ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"]
            
            async def fetch_chain(chain: str):
                try:
                    res = await moralis.get_wallet_token_balances(wallet_address, chain)
                    # Convert Moralis format to expected format
                    chain_tokens = []
                    for t in res:
                        # Moralis returns decimals, balance, usd_price, usd_value
                        balance = float(t.get("balance_formatted") or 0)
                        if balance <= 0:
                            continue
                        chain_tokens.append({
                            "mint": t.get("token_address", ""),
                            "name": t.get("name", ""),
                            "symbol": t.get("symbol", ""),
                            "logo": t.get("logo"),
                            "amount": balance,
                            "value_usd": float(t.get("usd_value") or 0),
                            "price_usd": float(t.get("usd_price") or 0),
                            "price_change_24h": float(t.get("usd_price_24hr_percent_change") or 0),
                            "chain": chain
                        })
                    return chain_tokens
                except Exception as e:
                    logger.warning(f"Error fetching Moralis {chain} tokens: {e}")
                    return []

            results = await asyncio.gather(*(fetch_chain(c) for c in evm_chains))
            for res in results:
                tokens.extend(res)
                
            await moralis.close()
        except Exception as e:
            logger.error(f"Error fetching EVM wallet tokens: {e}")
            
    return tokens


async def get_portfolio(request: web.Request) -> web.Response:
    """
    GET /api/v1/portfolio
    
    Get aggregated portfolio for all tracked wallets.
    Requires authentication.
    """
    user_wallet = get_user_wallet(request)

    if not user_wallet:
        return envelope_error_response(
            "Authentication required",
            code="AUTH_REQUIRED",
            http_status=401,
        )

    # Get tracked wallets from database
    wallets = []
    try:
        from src.storage.database import get_database
        db = await get_database()
        tracked = await db.get_tracked_wallets(user_wallet)
        wallets = [{'address': t.tracked_address, 'label': t.label} for t in tracked]
    except Exception as e:
        logger.warning(f"Failed to get tracked wallets: {e}")

    if not wallets:
        return envelope_response(
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
            value_usd = token.get('value_usd', 0)
            all_tokens.append(PortfolioTokenResponse(
                address=token.get('mint', ''),
                name=token.get('name', 'Unknown'),
                symbol=token.get('symbol', '???'),
                chain=token.get('chain', 'solana'),
                logo_url=token.get('logo'),
                balance=token.get('amount', 0),
                balance_usd=value_usd,
                price_usd=token.get('price_usd', 0),
                price_change_24h=token.get('price_change_24h', 0),
                safety_score=None,
                risk_level="UNKNOWN"
            ))
            total_value += value_usd

    health_score = _calculate_health_score(all_tokens, total_value)

    # Estimate 24h PnL from token price changes
    total_pnl_usd = sum(
        t.balance_usd * (t.price_change_24h / 100)
        for t in all_tokens
        if t.price_change_24h and t.balance_usd
    )
    total_pnl_percent = (total_pnl_usd / total_value * 100) if total_value > 0 else 0

    response = PortfolioResponse(
        wallet_address="aggregate",
        total_value_usd=total_value,
        total_pnl_usd=total_pnl_usd,
        total_pnl_percent=total_pnl_percent,
        tokens=all_tokens,
        health_score=health_score,
        last_updated=datetime.utcnow()
    ).model_dump(mode='json')

    return envelope_response(response)


async def get_wallet_portfolio(request: web.Request) -> web.Response:
    """
    GET /api/v1/portfolio/{wallet}
    
    Get portfolio for a specific wallet.
    Does not require authentication (public wallet data).
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

    # Fetch tokens using Helius
    tokens_raw = await get_wallet_tokens(wallet_address)

    tokens = []
    total_value = 0

    for token in tokens_raw:
        value = token.get('value_usd', 0)
        tokens.append(PortfolioTokenResponse(
            address=token.get('mint', ''),
            name=token.get('name', 'Unknown'),
            symbol=token.get('symbol', '???'),
            chain=token.get('chain', 'solana'),
            logo_url=token.get('logo'),
            balance=token.get('amount', 0),
            balance_usd=value,
            price_usd=token.get('price_usd', 0),
            price_change_24h=token.get('price_change_24h', 0),
            safety_score=None,
            risk_level="UNKNOWN"
        ))
        total_value += value

    health_score = _calculate_health_score(tokens, total_value)

    # Estimate 24h PnL from token price changes
    total_pnl_usd = sum(
        t.balance_usd * (t.price_change_24h / 100)
        for t in tokens
        if t.price_change_24h and t.balance_usd
    )
    total_pnl_percent = (total_pnl_usd / total_value * 100) if total_value > 0 else 0

    response = PortfolioResponse(
        wallet_address=wallet_address,
        total_value_usd=total_value,
        total_pnl_usd=total_pnl_usd,
        total_pnl_percent=total_pnl_percent,
        tokens=tokens,
        health_score=health_score,
        last_updated=datetime.utcnow()
    ).model_dump(mode='json')

    return web.json_response(response)


async def get_chain_parity_matrix(request: web.Request) -> web.Response:
    """GET /api/v1/portfolio/chains - return chain capability parity matrix."""
    del request

    class SolanaCapabilitiesProvider:
        def capability_overrides(self):
            return {
                "solana": {
                    "spot_holdings": {"supported": True, "reason": None},
                    "lp_positions": {"supported": False, "reason": "LP position tracking requires dedicated Solana DEX integrations"},
                    "lending_positions": {"supported": False, "reason": "Lending protocol integrations not yet available"},
                    "vault_positions": {"supported": False, "reason": "Vault integrations not yet available"},
                    "risk_decomposition": {"supported": False, "reason": "Requires position-level risk modeling"},
                    "alert_coverage": {"supported": False, "reason": "Alert system integration pending"},
                }
            }

    aggregator = MultiChainPortfolioAggregator(
        position_providers=[SolanaCapabilitiesProvider(), MoralisClient()]
    )
    snapshot = aggregator.aggregate([])
    payload = make_envelope(snapshot, meta={"matrix": "chain_parity_v1"})
    return web.json_response(payload)


async def get_tracked_wallets(request: web.Request) -> web.Response:
    """
    GET /api/v1/portfolio/wallets
    
    Get list of tracked wallets for the user.
    Requires authentication.
    """
    user_wallet = get_user_wallet(request)

    if not user_wallet:
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    # Get tracked wallets from database
    tracked_list = []
    try:
        from src.storage.database import get_database
        db = await get_database()
        tracked = await db.get_tracked_wallets(user_wallet)
        
        tracked_list = [
            TrackedWalletResponse(
                address=w.tracked_address,
                label=w.label,
                added_at=w.added_at,
                last_synced=w.last_synced,
                token_count=w.token_count or 0,
                total_value_usd=w.total_value_usd or 0
            )
            for w in tracked
        ]
    except Exception as e:
        logger.warning(f"Failed to get tracked wallets: {e}")

    return web.json_response(
        TrackedWalletsResponse(wallets=tracked_list).model_dump(mode='json')
    )


async def track_wallet(request: web.Request) -> web.Response:
    """
    POST /api/v1/portfolio/wallets
    
    Add a wallet to tracking.
    Requires authentication.
    """
    user_wallet = get_user_wallet(request)

    if not user_wallet:
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

    # Validate wallet address
    try:
        solana = SolanaClient(settings.solana_rpc_url)
        if not solana.is_valid_address(req.address):
            await solana.close()
            return web.json_response(
                ErrorResponse(error="Invalid wallet address", code="INVALID_ADDRESS").model_dump(mode='json'),
                status=400
            )
        await solana.close()
    except Exception:
        pass

    # Add to database
    try:
        from src.storage.database import get_database
        db = await get_database()
        
        # Check limit
        existing = await db.get_tracked_wallets(user_wallet)
        if len(existing) >= 10:
            return web.json_response(
                ErrorResponse(error="Maximum 10 wallets allowed", code="LIMIT_REACHED").model_dump(mode='json'),
                status=400
            )
        
        tracked = await db.add_tracked_wallet(
            owner_wallet=user_wallet,
            tracked_address=req.address,
            label=req.label
        )
        
        if tracked:
            return web.json_response(
                TrackedWalletResponse(
                    address=tracked.tracked_address,
                    label=tracked.label,
                    added_at=tracked.added_at,
                    last_synced=tracked.last_synced,
                    token_count=tracked.token_count or 0,
                    total_value_usd=tracked.total_value_usd or 0
                ).model_dump(mode='json'),
                status=201
            )
    except Exception as e:
        logger.error(f"Failed to track wallet: {e}")
        return web.json_response(
            ErrorResponse(error="Failed to track wallet", code="DATABASE_ERROR").model_dump(mode='json'),
            status=500
        )

    return web.json_response(
        ErrorResponse(error="Failed to track wallet", code="UNKNOWN_ERROR").model_dump(mode='json'),
        status=500
    )


async def untrack_wallet(request: web.Request) -> web.Response:
    """
    DELETE /api/v1/portfolio/wallets/{address}
    
    Remove a wallet from tracking.
    Requires authentication.
    """
    user_wallet = get_user_wallet(request)
    wallet_address = request.match_info.get('address')

    if not user_wallet:
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    if not wallet_address:
        return web.json_response(
            ErrorResponse(error="Wallet address required", code="MISSING_WALLET").model_dump(mode='json'),
            status=400
        )

    # Remove from database
    try:
        from src.storage.database import get_database
        db = await get_database()
        success = await db.remove_tracked_wallet(user_wallet, wallet_address)
        
        if not success:
            return web.json_response(
                ErrorResponse(error="Wallet not found", code="NOT_FOUND").model_dump(mode='json'),
                status=404
            )
    except Exception as e:
        logger.error(f"Failed to untrack wallet: {e}")
        return web.json_response(
            ErrorResponse(error="Failed to untrack wallet", code="DATABASE_ERROR").model_dump(mode='json'),
            status=500
        )

    return web.Response(status=204)


async def sync_wallet(request: web.Request) -> web.Response:
    """
    POST /api/v1/portfolio/wallets/{address}/sync
    
    Manually sync/refresh a tracked wallet's data.
    Requires authentication.
    """
    user_wallet = get_user_wallet(request)
    wallet_address = request.match_info.get('address')

    if not user_wallet:
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    if not wallet_address:
        return web.json_response(
            ErrorResponse(error="Wallet address required", code="MISSING_WALLET").model_dump(mode='json'),
            status=400
        )

    # Fetch current tokens
    tokens = await get_wallet_tokens(wallet_address)
    total_value = sum(t.get('value_usd', 0) for t in tokens)
    token_count = len(tokens)

    # Update database
    try:
        from src.storage.database import get_database
        db = await get_database()
        await db.update_tracked_wallet_stats(
            owner_wallet=user_wallet,
            tracked_address=wallet_address,
            token_count=token_count,
            total_value_usd=total_value
        )
    except Exception as e:
        logger.warning(f"Failed to update wallet stats: {e}")

    return web.json_response({
        "success": True,
        "wallet": wallet_address,
        "token_count": token_count,
        "total_value_usd": total_value,
        "synced_at": datetime.utcnow().isoformat()
    })


def setup_portfolio_routes(app: web.Application):
    """Setup portfolio API routes."""
    app.router.add_get('/api/v1/portfolio', get_portfolio)
    app.router.add_get('/api/v1/portfolio/wallets', get_tracked_wallets)
    app.router.add_post('/api/v1/portfolio/wallets', track_wallet)
    app.router.add_delete('/api/v1/portfolio/wallets/{address}', untrack_wallet)
    app.router.add_post('/api/v1/portfolio/wallets/{address}/sync', sync_wallet)
    app.router.add_get('/api/v1/portfolio/chains', get_chain_parity_matrix)
    app.router.add_get('/api/v1/portfolio/{wallet}', get_wallet_portfolio)

    logger.info("Portfolio routes registered with Helius integration")
