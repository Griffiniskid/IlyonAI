"""Tests for src/defi/execution/adapters/pendle_v2.py scaffold."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest, YieldQuoteRequest
from src.defi.execution.adapters.pendle_v2 import (
    PendleV2Adapter,
    SEL_ADD_LIQUIDITY_FROM_TOKEN,
    SEL_MINT_PY_FROM_TOKEN,
    SEL_SWAP_TOKEN_FOR_PT,
    _PENDLE_ROUTER,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def adapter():
    return PendleV2Adapter()


def test_router_addresses_present_per_chain():
    # Same canonical address across the 6 chains Pendle V2 is deployed.
    for chain in ("ethereum", "arbitrum", "optimism", "bsc", "base", "mantle"):
        assert chain in _PENDLE_ROUTER
        addr = _PENDLE_ROUTER[chain]
        assert addr.startswith("0x") and len(addr) == 42


def test_selectors_are_4bytes():
    for sel in (SEL_MINT_PY_FROM_TOKEN, SEL_SWAP_TOKEN_FOR_PT, SEL_ADD_LIQUIDITY_FROM_TOKEN):
        assert sel.startswith("0x") and len(sel) == 10


def test_supports_pendle_on_ethereum(adapter):
    r = adapter.supports(chain="ethereum", protocol="pendle-v2", action="deposit_lp")
    assert r.supported is True


def test_supports_pendle_canonical_alias(adapter):
    r = adapter.supports(chain="arbitrum", protocol="pendle", action="add_liquidity")
    assert r.supported is True


def test_refuses_unsupported_action(adapter):
    r = adapter.supports(chain="ethereum", protocol="pendle-v2", action="exotic")
    assert r.supported is False


def test_refuses_unsupported_chain(adapter):
    r = adapter.supports(chain="polygon", protocol="pendle-v2", action="deposit_lp")
    assert r.supported is False


def test_build_returns_pool_link_redirect_blocker(adapter):
    req = YieldBuildRequest(
        chain="ethereum", protocol="pendle-v2", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(adapter.build(req))
    assert len(steps) == 1
    assert "POOL_LINK_REDIRECT" in steps[0].blocker_codes
