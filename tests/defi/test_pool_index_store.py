"""Tests for src/defi/pool_index/store.py."""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from src.defi.pool_index.store import (
    find_pool_by_id,
    find_pool_by_pair,
    upsert_pool,
)


class _FakeSession:
    def __init__(self):
        self.statements: list[tuple[str, dict | None]] = []

    async def execute(self, statement, params=None, *a, **kw):
        self.statements.append((str(statement), params))

        class _R:
            def mappings(self):
                return self
            def all(self):
                return []
        return _R()


def test_upsert_emits_on_conflict_clause():
    session = _FakeSession()
    asyncio.run(upsert_pool(session, {
        "pool_id": "0xpool", "chain_id": 1, "protocol": "uniswap-v3",
        "token0_address": "0xa", "token1_address": "0xb",
        "tvl_usd": Decimal("1000"),
    }))
    sql_text, params = session.statements[0]
    assert "INSERT INTO pool_index" in sql_text
    assert "ON CONFLICT (pool_id) DO UPDATE" in sql_text
    assert params["pool_id"] == "0xpool"
    assert params["tvl_usd"] == Decimal("1000")


def test_find_by_pair_symmetric_match():
    session = _FakeSession()
    asyncio.run(find_pool_by_pair(
        session, chain_id=1, token0_address="0xA", token1_address="0xB",
    ))
    sql_text, params = session.statements[0]
    assert "(lower(token0_address) = :a AND lower(token1_address) = :b)" in sql_text
    assert "(lower(token0_address) = :b AND lower(token1_address) = :a)" in sql_text
    assert params["a"] == "0xa"
    assert params["b"] == "0xb"


def test_find_by_pair_protocol_filter():
    session = _FakeSession()
    asyncio.run(find_pool_by_pair(
        session, chain_id=1, token0_address="0xa", token1_address="0xb",
        protocol="uniswap-v3",
    ))
    sql_text, params = session.statements[0]
    assert "protocol = :protocol" in sql_text
    assert params["protocol"] == "uniswap-v3"


def test_find_by_pair_min_tvl_filter():
    session = _FakeSession()
    asyncio.run(find_pool_by_pair(
        session, chain_id=1, token0_address="0xa", token1_address="0xb",
        min_tvl_usd=10_000,
    ))
    sql_text, params = session.statements[0]
    assert "tvl_usd >= :min_tvl" in sql_text
    assert params["min_tvl"] == 10_000.0


def test_metadata_json_serialised():
    session = _FakeSession()
    asyncio.run(upsert_pool(session, {
        "pool_id": "0xpool", "chain_id": 1, "protocol": "uniswap-v3",
        "token0_address": "0xa", "token1_address": "0xb",
        "metadata_json": {"feed": "llama"},
    }))
    _, params = session.statements[0]
    assert json.loads(params["metadata_json"]) == {"feed": "llama"}
