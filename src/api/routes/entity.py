"""Entity graph API routes.

Provides entity listing, lookup, resolution, merging, and stats.
"""

import logging
from datetime import datetime

from aiohttp import web

from src.api.response_envelope import envelope_response, envelope_error_response
from src.smart_money.graph_store import GraphStore

logger = logging.getLogger(__name__)

GRAPH_STORE_KEY = web.AppKey("graph_store", GraphStore)


async def list_entities(request: web.Request) -> web.Response:
    """GET /api/v1/entities — list all known entities."""
    graph: GraphStore = request.app[GRAPH_STORE_KEY]
    entities = []
    for entity_id, record in graph.entities.items():
        wallets = graph.get_wallets_for_entity(entity_id)
        entities.append({
            "id": entity_id,
            "wallets": wallets,
            "reason": record.reason,
            "wallet_count": len(wallets),
            "label": record.label,
            "tags": record.tags,
            "risk_level": record.risk_level,
            "total_volume_usd": record.total_volume_usd,
            "chains": record.chains,
            "created_at": record.created_at,
            "last_active": record.last_active,
        })
    return envelope_response({"entities": entities}, meta={"surface": "entity_list"})


async def get_entity(request: web.Request) -> web.Response:
    """GET /api/v1/entities/{id} — get entity profile.

    Accepts either an entity ID or a wallet address.  When a wallet
    address is provided, it is resolved to the owning entity first.
    """
    lookup = request.match_info["id"]
    graph: GraphStore = request.app[GRAPH_STORE_KEY]

    # Try as entity ID first, then resolve as wallet address
    entity_id = lookup
    wallets = graph.get_wallets_for_entity(entity_id)
    if not wallets:
        resolved = graph.get_entity_id_for_wallet(lookup)
        if resolved:
            entity_id = resolved
            wallets = graph.get_wallets_for_entity(entity_id)

    if not wallets:
        return envelope_error_response(
            f"Entity {lookup} not found",
            code="ENTITY_NOT_FOUND",
            http_status=404,
        )

    record = graph.get_entity_record(entity_id)
    return envelope_response({
        "id": entity_id,
        "wallets": wallets,
        "reason": record.reason if record else None,
        "wallet_count": len(wallets),
        "label": record.label if record else None,
        "tags": record.tags if record else [],
        "risk_level": record.risk_level if record else None,
        "total_volume_usd": record.total_volume_usd if record else 0,
        "chains": record.chains if record else [],
        "created_at": record.created_at if record else None,
        "last_active": record.last_active if record else None,
    }, meta={"surface": "entity_profile"})


async def resolve_entity(request: web.Request) -> web.Response:
    """POST /api/v1/entities/resolve — resolve a wallet into an entity.

    Creates a new entity if the wallet isn't linked yet.
    Performs cross-chain resolution for EVM addresses.

    Body: {
        "wallet": "0x...",
        "chains": ["ethereum", "base", "arbitrum"]  // optional
    }
    """
    graph: GraphStore = request.app[GRAPH_STORE_KEY]

    try:
        body = await request.json()
    except Exception:
        return envelope_error_response(
            "Invalid JSON body", code="INVALID_JSON", http_status=400
        )

    wallet = body.get("wallet", "").strip().lower()
    if not wallet:
        return envelope_error_response(
            "Missing 'wallet' field", code="MISSING_FIELD", http_status=400
        )

    chains = body.get("chains", [])

    # Check if already resolved
    existing = graph.get_entity_id_for_wallet(wallet)
    if existing:
        record = graph.get_entity_record(existing)
        if chains and record:
            record.chains = list(set(record.chains + chains))
        wallets = graph.get_wallets_for_entity(existing)
        return envelope_response({
            "entity_id": existing,
            "wallets": wallets,
            "reason": record.reason if record else None,
            "status": "existing",
            "chains": record.chains if record else [],
        })

    # Cross-chain resolution for EVM addresses
    is_evm = wallet.startswith("0x") and len(wallet) == 42
    if is_evm and chains:
        entity_id = graph.resolve_cross_chain(wallet, chains)
    else:
        entity_id = graph.link_wallets(
            [wallet],
            f"Resolved via API at {datetime.utcnow().isoformat()}",
        )

    record = graph.get_entity_record(entity_id)
    return envelope_response({
        "entity_id": entity_id,
        "wallets": graph.get_wallets_for_entity(entity_id),
        "reason": record.reason if record else None,
        "status": "created",
        "chains": record.chains if record else [],
    })


async def merge_entities(request: web.Request) -> web.Response:
    """POST /api/v1/entities/merge — merge two entities.

    Body: {
        "entity_a": "entity-...",
        "entity_b": "entity-...",
        "reason": "Same operator confirmed"
    }
    """
    graph: GraphStore = request.app[GRAPH_STORE_KEY]

    try:
        body = await request.json()
    except Exception:
        return envelope_error_response(
            "Invalid JSON body", code="INVALID_JSON", http_status=400
        )

    entity_a = body.get("entity_a", "").strip()
    entity_b = body.get("entity_b", "").strip()
    reason = body.get("reason", "Manual merge")

    if not entity_a or not entity_b:
        return envelope_error_response(
            "Both 'entity_a' and 'entity_b' are required",
            code="MISSING_FIELD",
            http_status=400,
        )

    if entity_a == entity_b:
        return envelope_error_response(
            "Cannot merge an entity with itself",
            code="INVALID_MERGE",
            http_status=400,
        )

    new_id = graph.merge_entities(entity_a, entity_b, reason)
    if new_id is None:
        return envelope_error_response(
            "One or both entities not found",
            code="ENTITY_NOT_FOUND",
            http_status=404,
        )

    record = graph.get_entity_record(new_id)
    return envelope_response({
        "entity_id": new_id,
        "wallets": graph.get_wallets_for_entity(new_id),
        "reason": record.reason if record else None,
        "merged_from": [entity_a, entity_b],
    })


async def entity_stats(request: web.Request) -> web.Response:
    """GET /api/v1/entities/stats — entity graph statistics."""
    graph: GraphStore = request.app[GRAPH_STORE_KEY]
    return envelope_response(graph.get_stats(), meta={"surface": "entity_stats"})


async def add_wallet_to_entity(request: web.Request) -> web.Response:
    """POST /api/v1/entities/{id}/wallets — add a wallet to an entity.

    Body: { "wallet": "0x...", "reason": "Same deployer" }
    """
    entity_id = request.match_info["id"]
    graph: GraphStore = request.app[GRAPH_STORE_KEY]

    try:
        body = await request.json()
    except Exception:
        return envelope_error_response(
            "Invalid JSON body", code="INVALID_JSON", http_status=400
        )

    wallet = body.get("wallet", "").strip().lower()
    reason = body.get("reason", "")

    if not wallet:
        return envelope_error_response(
            "Missing 'wallet' field", code="MISSING_FIELD", http_status=400
        )

    success = graph.add_wallet_to_entity(entity_id, wallet, reason)
    if not success:
        return envelope_error_response(
            f"Entity {entity_id} not found",
            code="ENTITY_NOT_FOUND",
            http_status=404,
        )

    record = graph.get_entity_record(entity_id)
    return envelope_response({
        "entity_id": entity_id,
        "wallets": graph.get_wallets_for_entity(entity_id),
        "wallet_count": len(graph.get_wallets_for_entity(entity_id)),
    })


def setup_entity_routes(app: web.Application, graph_store: GraphStore | None = None):
    app[GRAPH_STORE_KEY] = graph_store or GraphStore()
    app.router.add_get("/api/v1/entities", list_entities)
    app.router.add_get("/api/v1/entities/stats", entity_stats)
    app.router.add_get("/api/v1/entities/{id}", get_entity)
    app.router.add_post("/api/v1/entities/resolve", resolve_entity)
    app.router.add_post("/api/v1/entities/merge", merge_entities)
    app.router.add_post("/api/v1/entities/{id}/wallets", add_wallet_to_entity)
