"""
Whale tracker API routes.

Provides endpoints for tracking large transactions and whale wallet activity.
Uses Helius API for real transaction data when available.
"""

import logging
import json
from aiohttp import web
from datetime import datetime
from typing import Dict, List, Optional, Any
import asyncio

from src.data.solana import SolanaClient
from src.data.dexscreener import DexScreenerClient
from src.analytics.behavior_adapters.evm import EVMBehaviorAdapter
from src.analytics.behavior_signals import BehaviorSignalBuilder
from src.api.schemas.responses import (
    WhaleActivityResponse, WhaleBehaviorResponse, WhaleTransactionResponse, WhaleProfileResponse,
    ErrorResponse
)
from src.api.response_envelope import envelope_error_response, envelope_response
from src.config import settings

logger = logging.getLogger(__name__)

_behavior_adapter = EVMBehaviorAdapter()
_behavior_builder = BehaviorSignalBuilder()

# Cache for whale transactions
_whale_cache: Dict[str, Any] = {}
_whale_cache_locks: Dict[str, asyncio.Lock] = {}
_cache_ttl = 300  # 5 minutes
_token_cache_ttl = 60  # 1 minute for token-specific feeds

# Known whale labels
KNOWN_WHALES = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": "Alameda",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Jump Trading",
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "Wintermute",
    "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm": "Circle",
    # Add more known whales as needed
}


def _get_or_create_lock(cache_key: str) -> asyncio.Lock:
    lock = _whale_cache_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _whale_cache_locks[cache_key] = lock
    return lock


def _is_cache_fresh(cached: Dict[str, Any], ttl_seconds: int) -> bool:
    cache_time = cached.get('time')
    if not isinstance(cache_time, datetime):
        return False
    age_seconds = (datetime.utcnow() - cache_time).total_seconds()
    return age_seconds < ttl_seconds


def _get_cached_data(cache_key: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
    cached = _whale_cache.get(cache_key)
    if not cached:
        return None

    if not _is_cache_fresh(cached, ttl_seconds):
        _whale_cache.pop(cache_key, None)
        return None

    return cached.get('data')


def _set_cached_data(cache_key: str, data: Dict[str, Any]) -> None:
    _whale_cache[cache_key] = {
        'data': data,
        'time': datetime.utcnow(),
    }


def _build_filtered_response(base_response: Dict[str, Any], type_filter: Optional[str], limit: int) -> Dict[str, Any]:
    transactions = base_response.get('transactions', [])
    if type_filter:
        transactions = [tx for tx in transactions if tx.get('type') == type_filter]

    response = dict(base_response)
    response['transactions'] = transactions[:limit]
    return response


def _collect_behavior_annotations(raw_transactions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    anomaly_flags: List[Dict[str, Any]] = []
    entity_heuristics: List[Dict[str, Any]] = []
    seen_anomalies = set()
    seen_heuristics = set()

    for tx in raw_transactions:
        for item in tx.get("anomaly_flags") or tx.get("anomalies") or []:
            key = json.dumps(item, sort_keys=True)
            if key in seen_anomalies:
                continue
            seen_anomalies.add(key)
            anomaly_flags.append(item)

        for item in tx.get("entity_heuristics") or tx.get("heuristics") or []:
            key = json.dumps(item, sort_keys=True)
            if key in seen_heuristics:
                continue
            seen_heuristics.add(key)
            entity_heuristics.append(item)

    return {
        "anomaly_flags": anomaly_flags,
        "entity_heuristics": entity_heuristics,
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
    raw_min_amount = request.query.get('min_amount_usd', '1000')
    raw_limit = request.query.get('limit', '50')
    token_filter = request.query.get('token')
    type_filter = request.query.get('type')
    if type_filter:
        type_filter = type_filter.lower()
    force_refresh = request.query.get('force_refresh', '').lower() in ('1', 'true')

    try:
        min_amount = float(raw_min_amount)
        limit = max(1, min(int(raw_limit), 200))
    except ValueError:
        return envelope_error_response(
            "Invalid query parameters",
            code="INVALID_PARAMS",
            details={"min_amount_usd": raw_min_amount, "limit": raw_limit},
            http_status=400,
        )

    if min_amount < 0:
        return envelope_error_response(
            "min_amount_usd must be non-negative",
            code="INVALID_PARAMS",
            http_status=400,
        )

    if type_filter and type_filter not in {'buy', 'sell'}:
        return envelope_error_response(
            "type must be 'buy' or 'sell'",
            code="INVALID_PARAMS",
            http_status=400,
        )

    # Cache all transaction types together and apply filters in-memory.
    cache_key = f"whales:{min_amount}:{token_filter or 'all'}"
    cache_lock = _get_or_create_lock(cache_key)

    try:
        async with cache_lock:
            base_response = None
            if not force_refresh:
                base_response = _get_cached_data(cache_key, _cache_ttl)

            if base_response is None:
                # Fetch a larger canonical set once, then filter/slice from cache.
                fetch_limit = 200

                solana = SolanaClient(
                    rpc_url=settings.solana_rpc_url,
                    helius_api_key=settings.helius_api_key
                )

                try:
                    if token_filter:
                        raw_transactions = await solana.get_token_whale_transactions(
                            token_address=token_filter,
                            min_amount_usd=min_amount,
                            limit=fetch_limit
                        )
                    else:
                        raw_transactions = await solana.get_recent_large_transactions(
                            min_amount_usd=min_amount,
                            limit=fetch_limit
                        )
                finally:
                    await solana.close()

                trades = []
                seen_signatures = set()
                for tx in raw_transactions:
                    try:
                        signature = tx.get('signature', '')
                        if signature and signature in seen_signatures:
                            continue
                        if signature:
                            seen_signatures.add(signature)

                        wallet_addr = tx.get('wallet_address', '')
                        wallet_label = tx.get('wallet_label') or KNOWN_WHALES.get(wallet_addr)

                        ts = tx.get('timestamp')
                        if isinstance(ts, str):
                            try:
                                timestamp = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            except Exception:
                                timestamp = datetime.utcnow()
                        elif isinstance(ts, datetime):
                            timestamp = ts
                        else:
                            timestamp = datetime.utcnow()

                        trades.append(WhaleTransactionResponse(
                            signature=signature,
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

                base_response = WhaleActivityResponse(
                    transactions=trades,
                    updated_at=datetime.utcnow(),
                    filter_token=token_filter,
                    min_amount_usd=min_amount
                ).model_dump(mode='json')

                _set_cached_data(cache_key, base_response)

            response = _build_filtered_response(base_response, type_filter, limit)

        return envelope_response(response)

    except Exception as e:
        logger.error(f"Whale activity error: {e}", exc_info=True)
        return envelope_error_response(
            "Failed to fetch whale activity",
            code="WHALE_FAILED",
            details={"message": str(e)},
            http_status=500,
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

    raw_min_amount = request.query.get('min_amount_usd', '1000')
    raw_limit = request.query.get('limit', '50')
    force_refresh = request.query.get('force_refresh', '').lower() in ('1', 'true')

    try:
        min_amount = float(raw_min_amount)
        limit = max(1, min(int(raw_limit), 200))
    except ValueError:
        return web.json_response(
            ErrorResponse(
                error="Invalid query parameters",
                code="INVALID_PARAMS",
                details={"min_amount_usd": raw_min_amount, "limit": raw_limit}
            ).model_dump(mode='json'),
            status=400
        )

    if min_amount < 0:
        return web.json_response(
            ErrorResponse(
                error="min_amount_usd must be non-negative",
                code="INVALID_PARAMS"
            ).model_dump(mode='json'),
            status=400
        )

    cache_key = f"whales:token:{token_address}:{min_amount}"
    cache_lock = _get_or_create_lock(cache_key)

    try:
        async with cache_lock:
            base_response = None
            if not force_refresh:
                base_response = _get_cached_data(cache_key, _token_cache_ttl)

            if base_response is None:
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

                solana = SolanaClient(
                    rpc_url=settings.solana_rpc_url,
                    helius_api_key=settings.helius_api_key
                )

                try:
                    raw_transactions = await solana.get_behavior_transactions(
                        token_address=token_address,
                        min_amount_usd=min_amount,
                        limit=200,
                        token_symbol=symbol,
                        token_name=name
                    )
                    behavior_inputs = _behavior_adapter.adapt(raw_transactions)
                    behavior_annotations = _collect_behavior_annotations(raw_transactions)
                finally:
                    await solana.close()

                trades = []
                seen_signatures = set()
                for tx in raw_transactions:
                    try:
                        signature = tx.get('signature', '')
                        if signature and signature in seen_signatures:
                            continue
                        if signature:
                            seen_signatures.add(signature)

                        wallet_addr = tx.get('wallet_address', '')
                        wallet_label = tx.get('wallet_label') or KNOWN_WHALES.get(wallet_addr)

                        ts = tx.get('timestamp')
                        if isinstance(ts, str):
                            try:
                                timestamp = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            except Exception:
                                timestamp = datetime.utcnow()
                        elif isinstance(ts, datetime):
                            timestamp = ts
                        else:
                            timestamp = datetime.utcnow()

                        trades.append(WhaleTransactionResponse(
                            signature=signature,
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

                base_response = WhaleActivityResponse(
                    transactions=trades,
                    updated_at=datetime.utcnow(),
                    filter_token=token_address,
                    min_amount_usd=min_amount,
                    behavior=WhaleBehaviorResponse.model_validate(
                        _behavior_builder.build(
                            whale_summary=behavior_inputs.get("whale_summary"),
                            concentration=behavior_inputs.get("concentration"),
                            anomalies=behavior_annotations.get("anomaly_flags"),
                            heuristics=behavior_annotations.get("entity_heuristics"),
                        ).to_dict()
                    ),
                ).model_dump(mode='json')

                _set_cached_data(cache_key, base_response)

            response = _build_filtered_response(base_response, None, limit)

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
        label = KNOWN_WHALES.get(wallet_address)

        # Fetch real whale transactions and filter to this wallet
        solana = SolanaClient(
            rpc_url=settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key,
        )
        try:
            all_txs = await solana.get_recent_large_transactions(
                min_amount_usd=1000, limit=200
            )
        finally:
            await solana.close()

        wallet_txs = [
            tx for tx in all_txs
            if tx.get("wallet_address") == wallet_address
        ]

        total_volume = sum(float(tx.get("amount_usd", 0)) for tx in wallet_txs)
        tokens_traded = len({tx.get("token_address") for tx in wallet_txs if tx.get("token_address")})

        recent = []
        for tx in wallet_txs[:20]:
            ts = tx.get("timestamp")
            if isinstance(ts, str):
                try:
                    timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    timestamp = datetime.utcnow()
            elif isinstance(ts, datetime):
                timestamp = ts
            else:
                timestamp = datetime.utcnow()

            recent.append(WhaleTransactionResponse(
                signature=tx.get("signature", ""),
                wallet_address=tx.get("wallet_address", ""),
                wallet_label=tx.get("wallet_label") or label,
                token_address=tx.get("token_address", ""),
                token_symbol=tx.get("token_symbol", "???"),
                token_name=tx.get("token_name", "Unknown"),
                type=tx.get("type", "buy"),
                amount_tokens=float(tx.get("amount_tokens", 0)),
                amount_usd=float(tx.get("amount_usd", 0)),
                price_usd=float(tx.get("price_usd", 0)),
                timestamp=timestamp,
                dex_name=tx.get("dex_name", "Unknown"),
            ))

        profile = WhaleProfileResponse(
            address=wallet_address,
            label=label,
            total_volume_usd=total_volume,
            transaction_count=len(wallet_txs),
            tokens_traded=tokens_traded,
            win_rate=None,
            avg_holding_time=None,
            recent_transactions=recent,
        ).model_dump(mode="json")

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
