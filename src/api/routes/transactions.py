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

from src.api.schemas.responses import ErrorResponse
from src.api.routes.auth import require_auth
from src.config import settings

logger = logging.getLogger(__name__)

async def get_transactions(request: web.Request) -> web.Response:
    """
    GET /api/v1/transactions/{wallet}
    
    Get transaction history for a wallet across multiple chains.
    """
    wallet_address = request.match_info.get('wallet')
    chain = request.query.get('chain', 'all')
    limit = int(request.query.get('limit', '50'))
    
    if not wallet_address:
        return web.json_response(
            ErrorResponse(error="Wallet address required", code="MISSING_WALLET").model_dump(mode='json'),
            status=400
        )
        
    # Placeholder for transaction fetching logic
    # Real implementation would call Moralis or Helius depending on chain
    transactions = []
    
    return web.json_response({
        "wallet": wallet_address,
        "chain": chain,
        "transactions": transactions,
        "total": len(transactions)
    })

async def export_transactions_csv(request: web.Request) -> web.Response:
    """
    GET /api/v1/transactions/{wallet}/export
    
    Export transaction history to CSV.
    """
    wallet_address = request.match_info.get('wallet')
    
    if not wallet_address:
        return web.json_response(
            ErrorResponse(error="Wallet address required", code="MISSING_WALLET").model_dump(mode='json'),
            status=400
        )
        
    # Fetch transactions (placeholder)
    transactions = []
    
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
