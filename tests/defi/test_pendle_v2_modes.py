"""Pendle V2 per-mode dispatch + expiry blocker."""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.pendle_v2 import (
    PendleV2Adapter,
    SEL_ADD_LIQUIDITY_FROM_TOKEN,
    SEL_MINT_PY_FROM_TOKEN,
    SEL_SWAP_TOKEN_FOR_PT,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _req(action: str | None = None, **over) -> YieldBuildRequest:
    extra = {"market": "0xabcabcabcabcabcabcabcabcabcabcabcabcabca"}
    if action:
        extra["action"] = action
    extra.update(over.pop("extra", {}))
    base = dict(
        chain="ethereum", protocol="pendle-v2", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        slippage_bps=100,
        extra=extra,
    )
    base.update(over)
    return YieldBuildRequest(**base)


def test_default_action_routes_to_add_liquidity_mode():
    a = PendleV2Adapter()
    steps = _run(a.build(_req()))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "add_liquidity"
    assert SEL_ADD_LIQUIDITY_FROM_TOKEN in s.description
    assert "NEEDS_FRONTEND_SDK" in s.blocker_codes


def test_mint_py_action_routes_to_mint_py_selector():
    a = PendleV2Adapter()
    steps = _run(a.build(_req(action="mint_py")))
    assert steps[0].action == "mint_py"
    assert SEL_MINT_PY_FROM_TOKEN in steps[0].description


def test_swap_for_pt_action_routes_to_swap_selector():
    a = PendleV2Adapter()
    steps = _run(a.build(_req(action="swap_for_pt")))
    assert steps[0].action == "swap_for_pt"
    assert SEL_SWAP_TOKEN_FOR_PT in steps[0].description


def test_expired_market_returns_epoch_blocker():
    a = PendleV2Adapter()
    # 2020-01-01 — well in the past.
    expired_ts = 1577836800
    req = _req(extra={"market_expiry_ts": expired_ts})
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert "PENDING_EPOCH_ENTRY" in steps[0].blocker_codes


def test_future_market_skips_epoch_blocker():
    a = PendleV2Adapter()
    future_ts = int(time.time()) + 86400 * 30  # 30 days out
    req = _req(extra={"market_expiry_ts": future_ts})
    steps = _run(a.build(req))
    assert "PENDING_EPOCH_ENTRY" not in steps[0].blocker_codes


def test_missing_market_raises():
    a = PendleV2Adapter()
    req = _req()
    req.extra.pop("market")
    with pytest.raises(ValueError, match="extra.market"):
        _run(a.build(req))


def test_unsupported_chain_raises():
    a = PendleV2Adapter()
    req = _req(chain="polygon")
    with pytest.raises(ValueError, match="Pendle V2 router not registered"):
        _run(a.build(req))


def test_selector_constants_pinned():
    """Regression pin: Pendle V4 router dispatcher selectors must not drift."""
    assert SEL_MINT_PY_FROM_TOKEN == "0xc81f847a"
    assert SEL_SWAP_TOKEN_FOR_PT == "0x594a88cc"
    assert SEL_ADD_LIQUIDITY_FROM_TOKEN == "0x9f9da99e"
