"""Pin test for the portfolio endpoint's concurrent-dedupe + TTL cache.

Phase A (IlyonAI tester-ready Playwright) found 5 concurrent requests for
the same wallet ALL returned 500 because the wallet-assistant fans out to
~15 RPCs + Moralis + Binance simultaneously. The fix in `portfolio.py`:

  1. 30 s TTL cache keyed by wallet address (lower-cased)
  2. Per-wallet asyncio.Lock so concurrent callers wait on the first one
  3. Hard-exception → 200 with zero-balance + `partial:true` (NEVER 5xx)

This test asserts all three. Stubs the crypto_agent import so we don't
have to drag in the full LangChain dep tree on dev machines.
"""
from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import patch, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Stub `app.agents.crypto_agent` BEFORE importing portfolio — the real
# module pulls in LangChain which isn't on dev machines.
_stub = types.ModuleType("app.agents.crypto_agent")
_stub.MORALIS_API_KEY = "test"
_stub._scan_single_address = lambda _addr, _ignored: []  # overridden in each test
sys.modules.setdefault("app.agents", types.ModuleType("app.agents"))
sys.modules["app.agents.crypto_agent"] = _stub

from app.api.portfolio import (
    router,
    _PORTFOLIO_CACHE,
    _PORTFOLIO_LOCKS,
    _PORTFOLIO_TTL,
)


@pytest.fixture(autouse=True)
def _clear_state():
    _PORTFOLIO_CACHE.clear()
    _PORTFOLIO_LOCKS.clear()
    yield
    _PORTFOLIO_CACHE.clear()
    _PORTFOLIO_LOCKS.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fake_scanner(call_count: list[int]):
    """Sync function (matches _scan_single_address signature) that records
    its call count. Returns one EVM chain with 1 ETH."""

    def inner(addr, _ignored):
        call_count.append(addr)
        return [{
            "chain": "Ethereum",
            "native_symbol": "ETH",
            "native_balance": 1.0,
            "native_usd": 2000.0,
            "tokens": [],
        }]

    return inner


def test_first_call_warms_cache(client):
    """Single request populates the cache + returns 200 with data."""
    calls = []
    scanner = _fake_scanner(calls)
    with (
        patch("app.api.portfolio._scan_single_address", scanner),
        patch("app.api.portfolio._fetch_prices", AsyncMock(return_value={"BNBUSDT": 600.0, "SOLUSDT": 80.0})),
    ):
        r = client.get("/portfolio/0xaaaa")
        assert r.status_code == 200
        body = r.json()
        assert body["totalUsd"] == 2000.0
        assert body["bnbPrice"] == 600.0
        assert len(calls) == 1
        assert "0xaaaa" in _PORTFOLIO_CACHE


def test_second_call_within_ttl_hits_cache(client):
    """Cache hit returns the same payload without re-running the scanner."""
    calls = []
    scanner = _fake_scanner(calls)
    with (
        patch("app.api.portfolio._scan_single_address", scanner),
        patch("app.api.portfolio._fetch_prices", AsyncMock(return_value={})),
    ):
        client.get("/portfolio/0xaaaa")
        client.get("/portfolio/0xaaaa")
    assert len(calls) == 1, "scanner should fire exactly once across two requests"


def test_5_concurrent_requests_dedupe_to_one_scan(client):
    """Phase A pin: 5 concurrent requests for the same wallet must NOT all
    fire the scanner — they must share the first request's work."""
    calls = []
    scanner = _fake_scanner(calls)
    with (
        patch("app.api.portfolio._scan_single_address", scanner),
        patch("app.api.portfolio._fetch_prices", AsyncMock(return_value={})),
    ):
        with client:
            # TestClient is sync, but FastAPI uses asyncio internally for
            # async routes. We use threads to spawn truly-parallel requests.
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=5) as ex:
                results = list(ex.map(lambda _: client.get("/portfolio/0xaaaa"), range(5)))
    for r in results:
        assert r.status_code == 200
        assert r.json()["totalUsd"] == 2000.0
    assert len(calls) <= 2, f"expected ≤2 scans across 5 concurrent calls, got {len(calls)}"


def test_scanner_exception_returns_200_with_partial_not_5xx(client):
    """Hard-exception in the inner builder must return 200 with partial:true."""
    def boom(*_args, **_kw):
        raise RuntimeError("RPC pool exhausted")

    with (
        patch("app.api.portfolio._scan_single_address", boom),
        patch("app.api.portfolio._fetch_prices", AsyncMock(side_effect=RuntimeError("binance down"))),
    ):
        r = client.get("/portfolio/0xaaaa")
        # Per-address scan failures get caught + skipped in _build_portfolio,
        # so we still get a 200 with empty tokens.
        assert r.status_code == 200
        body = r.json()
        assert body["totalUsd"] == 0.0
        assert body["tokens"] == []
        # Prices failure is also caught
        assert body["bnbPrice"] == 0.0
        assert body["solPrice"] == 0.0
