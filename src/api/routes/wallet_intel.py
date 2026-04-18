"""
Wallet intelligence API routes.

Provides profile aggregation, forensics analysis, and on-chain
enrichment for individual wallets across all supported chains.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from aiohttp import web

from src.api.response_envelope import envelope_response, envelope_error_response
from src.chains.base import ChainType
from src.chains.registry import ChainRegistry
from src.config import settings

logger = logging.getLogger(__name__)

# Known whale labels (mirrored from whale.py for fast local lookups)
KNOWN_WHALES = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": "Alameda",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Jump Trading",
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "Wintermute",
    "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm": "Circle",
}


def _is_evm_address(address: str) -> bool:
    return address.startswith("0x") and len(address) == 42


async def _enrich_evm_wallet(address: str) -> Dict[str, Any]:
    """Fetch on-chain data for an EVM wallet from public RPCs."""
    registry = ChainRegistry.get_instance()
    registry.initialize(settings)

    chain_balances = {}
    total_native_usd = 0.0

    async def check_chain(chain: ChainType):
        try:
            client = registry.get_client(chain)
            balance = await client.get_native_balance(address)
            return chain.value, {
                "native_balance": balance,
                "native_token": chain.native_token_symbol,
                "has_activity": balance > 0,
            }
        except Exception:
            return chain.value, {"native_balance": 0, "native_token": chain.native_token_symbol, "has_activity": False}

    evm_chains = registry.get_evm_chains()
    results = await asyncio.gather(
        *[check_chain(c) for c in evm_chains],
        return_exceptions=True,
    )

    active_chains = []
    for result in results:
        if isinstance(result, Exception):
            continue
        chain_name, data = result
        chain_balances[chain_name] = data
        if data.get("has_activity"):
            active_chains.append(chain_name)

    return {
        "chain_balances": chain_balances,
        "active_chains": active_chains,
        "active_chain_count": len(active_chains),
        "is_multi_chain": len(active_chains) > 1,
    }


async def _enrich_solana_wallet(address: str) -> Dict[str, Any]:
    """Fetch on-chain data for a Solana wallet."""
    registry = ChainRegistry.get_instance()
    registry.initialize(settings)

    try:
        client = registry.get_client(ChainType.SOLANA)
        balance = await client.get_native_balance(address)
        return {
            "chain_balances": {
                "solana": {
                    "native_balance": balance,
                    "native_token": "SOL",
                    "has_activity": balance > 0,
                }
            },
            "active_chains": ["solana"] if balance > 0 else [],
            "active_chain_count": 1 if balance > 0 else 0,
            "is_multi_chain": False,
        }
    except Exception as e:
        logger.warning(f"Solana wallet enrichment failed for {address}: {e}")
        return {
            "chain_balances": {},
            "active_chains": [],
            "active_chain_count": 0,
            "is_multi_chain": False,
        }


async def get_wallet_profile(request: web.Request) -> web.Response:
    """
    GET /api/v1/wallets/{address}/profile

    Aggregate wallet profile from whale transactions, known labels,
    the entity graph, and on-chain data across all supported chains.
    """
    address = request.match_info["address"]
    label = KNOWN_WHALES.get(address)

    volume_usd = 0.0
    tx_count = 0
    recent_transactions: List[Dict[str, Any]] = []

    # Fetch DB data and on-chain enrichment in parallel
    db_task = _fetch_db_profile(address)
    if _is_evm_address(address):
        enrich_task = _enrich_evm_wallet(address)
    else:
        enrich_task = _enrich_solana_wallet(address)

    db_result, on_chain = await asyncio.gather(
        db_task, enrich_task, return_exceptions=True,
    )

    if isinstance(db_result, Exception):
        db_result = {"volume_usd": 0, "tx_count": 0, "transactions": [], "label": None}
    if isinstance(on_chain, Exception):
        on_chain = {"chain_balances": {}, "active_chains": [], "active_chain_count": 0, "is_multi_chain": False}

    volume_usd = db_result.get("volume_usd", 0)
    tx_count = db_result.get("tx_count", 0)
    recent_transactions = db_result.get("transactions", [])
    if not label:
        label = db_result.get("label")

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

                # Auto cross-chain resolve for EVM addresses
                if _is_evm_address(address) and on_chain.get("active_chains"):
                    graph_store.resolve_cross_chain(address, on_chain["active_chains"])
    except Exception:
        pass

    # GoPlus address security check for EVM wallets
    address_security = None
    if _is_evm_address(address):
        try:
            from src.data.goplus import GoPlusClient
            gp = GoPlusClient(api_key=settings.goplus_api_key)
            try:
                address_security = await gp.check_address_security(address, ChainType.ETHEREUM)
            finally:
                await gp.close()
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
        "on_chain": on_chain,
        "address_security": address_security,
        "recent_transactions": recent_transactions,
    })


async def _fetch_db_profile(address: str) -> Dict[str, Any]:
    """Fetch profile data from the database."""
    try:
        from src.storage.database import get_database
        db = await get_database()
        txs = await db.get_whale_transactions_for_wallet(address, hours=24, limit=50)
        volume_usd = 0.0
        label = None
        for tx in txs:
            volume_usd += float(tx.get("amount_usd", 0))
            if not label and tx.get("wallet_label"):
                label = tx["wallet_label"]
        return {
            "volume_usd": volume_usd,
            "tx_count": len(txs),
            "transactions": txs,
            "label": label,
        }
    except Exception as exc:
        logger.warning("Failed to fetch wallet profile from DB: %s", exc)
        return {"volume_usd": 0, "tx_count": 0, "transactions": [], "label": None}


async def get_wallet_forensics(request: web.Request) -> web.Response:
    """
    GET /api/v1/wallets/{address}/forensics

    Return risk analysis produced by the WalletForensicsEngine.
    Returns HTTP 503 if the engine fails or is unavailable.
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


async def get_wallet_balances(request: web.Request) -> web.Response:
    """
    GET /api/v1/wallets/{address}/balances

    Get native token balances across all chains.
    No API keys required - uses public RPCs.
    """
    address = request.match_info["address"]

    if _is_evm_address(address):
        data = await _enrich_evm_wallet(address)
    else:
        data = await _enrich_solana_wallet(address)

    return envelope_response({
        "wallet": address,
        **data,
    })


def setup_wallet_intel_routes(app: web.Application):
    """Register wallet intelligence API routes."""
    app.router.add_get("/api/v1/wallets/{address}/profile", get_wallet_profile)
    app.router.add_get("/api/v1/wallets/{address}/forensics", get_wallet_forensics)
    app.router.add_get("/api/v1/wallets/{address}/balances", get_wallet_balances)
    logger.info("Wallet intel routes registered")
