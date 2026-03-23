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
        return envelope_error_response(
            "Wallet address required",
            code="MISSING_WALLET",
            http_status=400,
        )

    if limit is None:
        return envelope_error_response(
            f"limit must be an integer between {MIN_LIMIT} and {MAX_LIMIT}",
            code="INVALID_REQUEST",
            http_status=400,
        )
        
    transactions: List[Dict] = []

    if chain in ("all", "solana") and settings.helius_api_key:
        try:
            url = (
                f"https://api.helius.xyz/v0/addresses/{wallet_address}/transactions"
                f"?api-key={settings.helius_api_key}&limit={min(limit, 100)}"
            )
            async with _aiohttp.ClientSession() as session:
                async with session.get(url, timeout=_aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        raw = await resp.json()
                        for tx in (raw if isinstance(raw, list) else []):
                            sig = tx.get("signature", "")
                            ts = tx.get("timestamp", 0)
                            tx_type = tx.get("type", "UNKNOWN")
                            desc = tx.get("description", "")
                            fee = tx.get("fee", 0)

                            transactions.append({
                                "hash": sig,
                                "chain": "solana",
                                "type": tx_type,
                                "description": desc,
                                "fee_lamports": fee,
                                "timestamp": ts,
                                "status": "confirmed",
                            })
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
        return envelope_error_response(
            "Wallet address required",
            code="MISSING_WALLET",
            http_status=400,
        )
        
    transactions: List[Dict] = []
    if settings.helius_api_key:
        try:
            url = (
                f"https://api.helius.xyz/v0/addresses/{wallet_address}/transactions"
                f"?api-key={settings.helius_api_key}&limit=100"
            )
            async with _aiohttp.ClientSession() as session:
                async with session.get(url, timeout=_aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        raw = await resp.json()
                        for tx in (raw if isinstance(raw, list) else []):
                            transactions.append({
                                "date": tx.get("timestamp", ""),
                                "chain": "solana",
                                "type": tx.get("type", "UNKNOWN"),
                                "hash": tx.get("signature", ""),
                                "status": "confirmed",
                                "amount": "",
                                "symbol": "",
                                "usd_value": "",
                            })
        except Exception as exc:
            logger.warning("Failed to fetch transactions for CSV export: %s", exc)
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Chain', 'Type', 'Hash', 'Status', 'Amount', 'Symbol', 'USD Value'])
    
    for tx in transactions:
        writer.writerow([
            tx.get('date', ''),
            tx.get('chain', ''),
            tx.get('type', ''),
            tx.get('hash', ''),
            tx.get('status', ''),
            tx.get('amount', ''),
            tx.get('symbol', ''),
            tx.get('usd_value', '')
        ])
        
    csv_data = output.getvalue()
    output.close()
    
    return web.Response(
        text=csv_data,
        content_type='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{wallet_address}_transactions.csv"'
        }
    )

def setup_transactions_routes(app: web.Application):
    """Setup transaction history API routes."""
    app.router.add_get('/api/v1/transactions/{wallet}', get_transactions)
    app.router.add_get('/api/v1/transactions/{wallet}/export', export_transactions_csv)
    logger.info("Transaction history routes registered")
