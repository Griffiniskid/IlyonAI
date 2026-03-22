import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.smart_money.graph_store import GraphStore


@pytest.mark.asyncio
async def test_entity_list_returns_entities():
    """Entity list endpoint should return entities from graph store."""
    from src.api.routes.entity import setup_entity_routes

    app = web.Application()
    graph = GraphStore()
    entity_id = graph.link_wallets(["wallet1", "wallet2"], reason="co-funded")

    setup_entity_routes(app, graph_store=graph)

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        resp = await client.get("/api/v1/entities")
        assert resp.status == 200
        body = await resp.json()
        entities = body["data"]["entities"]
        assert len(entities) == 1
        assert entities[0]["id"] == entity_id
        assert set(entities[0]["wallets"]) == {"wallet1", "wallet2"}
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
async def test_entity_detail_returns_profile():
    """Entity detail endpoint should return entity profile."""
    from src.api.routes.entity import setup_entity_routes

    app = web.Application()
    graph = GraphStore()
    entity_id = graph.link_wallets(["walletA"], reason="whale-cluster")

    setup_entity_routes(app, graph_store=graph)

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        resp = await client.get(f"/api/v1/entities/{entity_id}")
        assert resp.status == 200
        body = await resp.json()
        assert body["data"]["id"] == entity_id
        assert body["data"]["reason"] == "whale-cluster"

        # 404 for unknown entity
        resp404 = await client.get("/api/v1/entities/entity-nonexistent")
        assert resp404.status == 404
    finally:
        await client.close()
        await server.close()
