"""Entity graph API routes."""

import logging

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
        reason = graph.get_link_reason_for_entity(entity_id)
        entities.append({
            "id": entity_id,
            "wallets": wallets,
            "reason": reason,
            "wallet_count": len(wallets),
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

    reason = graph.get_link_reason_for_entity(entity_id)
    return envelope_response({
        "id": entity_id,
        "wallets": wallets,
        "reason": reason,
        "wallet_count": len(wallets),
    }, meta={"surface": "entity_profile"})


def setup_entity_routes(app: web.Application, graph_store: GraphStore | None = None):
    app[GRAPH_STORE_KEY] = graph_store or GraphStore()
    app.router.add_get("/api/v1/entities", list_entities)
    app.router.add_get("/api/v1/entities/{id}", get_entity)
