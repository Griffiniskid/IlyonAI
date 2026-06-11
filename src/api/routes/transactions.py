"""
Transaction history API routes.

Provides endpoints for fetching multi-chain wallet transaction history
and exporting it to CSV.
"""

import logging
from aiohttp import web
from typing import Dict, List, Optional
import csv
import io

import aiohttp as _aiohttp

from src.api.response_envelope import envelope_error_response, envelope_response
from src.config import settings

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MIN_LIMIT = 1
MAX_LIMIT = 500


async def _fetch_helius_wallet_txs(wallet_address: str, limit: int) -> List[Dict]:
    """Fetch + map a wallet's Helius enhanced transactions, failing over across
    Helius keys (shared pool) when one returns HTTP 429 ('max usage reached')."""
    from src.data.helius_keys import (
        get_active_helius_key,
        mark_helius_key_exhausted,
        get_helius_pool,
    )

    out: List[Dict] = []
    max_attempts = max(2, get_helius_pool().key_count() + 1)
    for attempt in range(max_attempts):
        key = get_active_helius_key()
        if not key:
            return out
        url = (
            f"https://api.helius.xyz/v0/addresses/{wallet_address}/transactions"
            f"?api-key={key}&limit={min(limit, 100)}"
        )
        async with _aiohttp.ClientSession() as session:
            async with session.get(url, timeout=_aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 429:
                    nxt = mark_helius_key_exhausted(key)
                    if nxt and nxt != key and attempt < max_attempts - 1:
                        continue  # fail over to the next key and retry
                    return out
                if resp.status != 200:
                    return out
                raw = await resp.json()
        for tx in (raw if isinstance(raw, list) else []):
            out.append({
                "hash": tx.get("signature", ""),
                "chain": "solana",
                "type": tx.get("type", "UNKNOWN"),
                "description": tx.get("description", ""),
                "fee_lamports": tx.get("fee", 0),
                "timestamp": tx.get("timestamp", 0),
                "status": "confirmed",
            })
        return out
    return out


def _parse_limit(raw_limit: str | None) -> int | None:
    if raw_limit is None:
        return DEFAULT_LIMIT

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return None

    if limit < MIN_LIMIT or limit > MAX_LIMIT:
        return None

    return limit

async def get_transactions(request: web.Request) -> web.Response:
    """
    GET /api/v1/transactions/{wallet}

    Get transaction history for a wallet across multiple chains.
    """
    wallet_address = request.match_info.get('wallet')
    chain = request.query.get('chain', 'all')
    limit = _parse_limit(request.query.get('limit'))

    if not wallet_address:
        return envelope_error_response("Wallet address required", code="MISSING_WALLET", http_status=400)
    if limit is None:
        return envelope_error_response(
            f"limit must be an integer between {MIN_LIMIT} and {MAX_LIMIT}",
            code="INVALID_REQUEST", http_status=400,
        )

    transactions: List[Dict] = []

    from src.data.helius_keys import get_active_helius_key
    if chain in ("all", "solana") and get_active_helius_key():
        # Check DB cache first (5-minute TTL)
        from src.storage.database import get_database
        db = await get_database()
        cached = await db.get_cached_transactions(wallet_address, "solana", max_age_seconds=300)

        if cached is not None:
            transactions = cached
        else:
            try:
                transactions = await _fetch_helius_wallet_txs(wallet_address, limit)
                # Cache the result
                await db.set_cached_transactions(wallet_address, "solana", transactions)
            except Exception as exc:
                logger.warning("Failed to fetch transactions from Helius: %s", exc)

    return envelope_response({
        "wallet": wallet_address,
        "chain": chain,
        "limit": limit,
        "transactions": transactions[:limit],
        "total": len(transactions),
    })

async def export_transactions_csv(request: web.Request) -> web.Response:
    """
    GET /api/v1/transactions/{wallet}/export

    Export transaction history to CSV.
    """
    wallet_address = request.match_info.get('wallet')
    if not wallet_address:
        return envelope_error_response("Wallet address required", code="MISSING_WALLET", http_status=400)

    transactions: List[Dict] = []
    from src.data.helius_keys import get_active_helius_key
    if get_active_helius_key():
        from src.storage.database import get_database
        db = await get_database()
        cached = await db.get_cached_transactions(wallet_address, "solana", max_age_seconds=300)
        if cached is not None:
            transactions = cached
        else:
            try:
                transactions = await _fetch_helius_wallet_txs(wallet_address, 100)
                await db.set_cached_transactions(wallet_address, "solana", transactions)
            except Exception as exc:
                logger.warning("Failed to fetch transactions for CSV export: %s", exc)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Chain', 'Type', 'Hash', 'Status', 'Description', 'Fee'])
    for tx in transactions:
        writer.writerow([
            tx.get('timestamp', ''), tx.get('chain', ''), tx.get('type', ''),
            tx.get('hash', ''), tx.get('status', ''), tx.get('description', ''),
            tx.get('fee_lamports', ''),
        ])
    csv_data = output.getvalue()
    output.close()

    return web.Response(
        text=csv_data, content_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{wallet_address}_transactions.csv"'},
    )

def setup_transactions_routes(app: web.Application):
    """Setup transaction history API routes."""
    app.router.add_get('/api/v1/transactions/{wallet}', get_transactions)
    app.router.add_get('/api/v1/transactions/{wallet}/export', export_transactions_csv)
    logger.info("Transaction history routes registered")
