"""
Wallet intelligence API routes.

Provides profile aggregation and forensics analysis for individual wallets.
"""

import logging
from typing import Any, Dict, List

from aiohttp import web

from src.api.response_envelope import envelope_response, envelope_error_response

logger = logging.getLogger(__name__)

# Known whale labels (mirrored from whale.py for fast local lookups)
KNOWN_WHALES = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": "Alameda",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Jump Trading",
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "Wintermute",
    "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm": "Circle",
}


async def get_wallet_profile(request: web.Request) -> web.Response:
    """
    GET /api/v1/wallets/{address}/profile

    Aggregate wallet profile from whale transactions, known labels,
    and the entity graph.
    """
    address = request.match_info["address"]
    label = KNOWN_WHALES.get(address)

    volume_usd = 0.0
    tx_count = 0
    recent_transactions: List[Dict[str, Any]] = []

    try:
        from src.storage.database import get_database
        db = await get_database()
        txs = await db.get_whale_transactions_for_wallet(address, hours=24, limit=50)
        for tx in txs:
            amount = float(tx.get("amount_usd", 0))
            volume_usd += amount
            tx_count += 1
            recent_transactions.append(tx)
            if not label and tx.get("wallet_label"):
                label = tx["wallet_label"]
    except Exception as exc:
        logger.warning("Failed to fetch wallet profile from DB: %s", exc)

    # Entity graph lookup (best-effort)
    entity_id = None
    linked_wallets: List[str] = []
    link_reason = None
    try:
        from src.api.routes.entity import GRAPH_STORE_KEY
        graph_store = request.app.get(GRAPH_STORE_KEY)
        if graph_store:
            entity_id = graph_store.get_entity_id_for_wallet(address)
            if entity_id:
                linked_wallets = graph_store.get_wallets_for_entity(entity_id)
                link_reason = graph_store.get_link_reason_for_entity(entity_id)
    except Exception:
        pass

    return envelope_response({
        "wallet": address,
        "label": label,
        "volume_usd": volume_usd,
        "transaction_count": tx_count,
        "entity_id": entity_id,
        "linked_wallets": linked_wallets,
        "link_reason": link_reason,
        "recent_transactions": recent_transactions,
    })


async def get_wallet_forensics(request: web.Request) -> web.Response:
    """
    GET /api/v1/wallets/{address}/forensics

    Return risk analysis produced by the WalletForensicsEngine.
    Falls back to a degraded response if the engine is unavailable.
    """
    address = request.match_info["address"]

    try:
        from src.analytics.wallet_forensics import WalletForensicsEngine

        engine = WalletForensicsEngine()
        result = await engine.analyze_wallet(address)

        return envelope_response({
            "risk_level": result.risk_level.value,
            "reputation_score": result.reputation_score,
            "tokens_deployed": result.tokens_deployed,
            "rugged_tokens": result.rugged_tokens,
            "active_tokens": result.active_tokens,
            "rug_percentage": result.rug_percentage,
            "patterns_detected": result.patterns_detected,
            "pattern_severity": result.pattern_severity,
            "funding_risk": result.funding_risk,
            "confidence": result.confidence,
            "evidence_summary": result.evidence_summary,
        })
    except Exception as exc:
        logger.error("Forensics analysis failed for %s: %s", address, exc, exc_info=True)
        return envelope_error_response(
            "Forensics analysis failed",
            code="FORENSICS_FAILED",
            details={"message": str(exc)},
            http_status=503,
        )


def setup_wallet_intel_routes(app: web.Application):
    """Register wallet intelligence API routes."""
    app.router.add_get("/api/v1/wallets/{address}/profile", get_wallet_profile)
    app.router.add_get("/api/v1/wallets/{address}/forensics", get_wallet_forensics)
    logger.info("Wallet intel routes registered")
