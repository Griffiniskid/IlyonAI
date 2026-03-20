from contextlib import asynccontextmanager

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.config import settings
from src.portfolio.multichain_aggregator import CAPABILITIES


@asynccontextmanager
async def portfolio_client():
    app = web.Application()

    from src.api.routes.portfolio import setup_portfolio_routes

    setup_portfolio_routes(app)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chain_parity_matrix_route_returns_required_shape():
    async with portfolio_client() as client:
        response = await client.get("/api/v1/portfolio/chains")
        payload = await response.json()

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["meta"]["matrix"] == "chain_parity_v1"
    assert payload["errors"] == []
    assert payload["freshness"] == "live"

    data = payload["data"]
    assert set(data["chains"]) == set(settings.portfolio_required_chains)
    assert set(data["capabilities"]) == set(CAPABILITIES)

    for chain in settings.portfolio_required_chains:
        chain_row = data["chains"][chain]
        assert set(chain_row) == set(CAPABILITIES)
        for capability in CAPABILITIES:
            cell = chain_row[capability]
            assert set(cell) == {"state", "reason"}
            assert cell["state"] in {"available", "degraded"}
            if cell["state"] == "degraded":
                assert cell["reason"]


@pytest.mark.asyncio
async def test_chain_parity_matrix_route_includes_degraded_reason():
    async with portfolio_client() as client:
        response = await client.get("/api/v1/portfolio/chains")
        payload = await response.json()

    assert response.status == 200
    matrix = payload["data"]["chains"]
    degraded_cells = [
        cell
        for chain_row in matrix.values()
        for cell in chain_row.values()
        if cell["state"] == "degraded"
    ]
    assert degraded_cells
    assert all(cell["reason"] for cell in degraded_cells)


@pytest.mark.asyncio
async def test_chain_parity_matrix_route_requires_explicit_support_for_full_coverage():
    async with portfolio_client() as client:
        response = await client.get("/api/v1/portfolio/chains")
        payload = await response.json()

    assert response.status == 200
    matrix = payload["data"]["chains"]
    for chain_row in matrix.values():
        assert any(cell["state"] == "degraded" for cell in chain_row.values())
