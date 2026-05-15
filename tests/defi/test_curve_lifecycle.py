"""Tests for Curve remove_liquidity_one_coin lifecycle."""
from __future__ import annotations

import asyncio
from decimal import Decimal

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.curve import CurveSingleSidedAdapter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_remove_one_coin_selector_3pool_usdc():
    a = CurveSingleSidedAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="curve", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw", "pool_key": "3pool"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert steps[0].action == "remove_liquidity_one_coin"
    # remove_liquidity_one_coin selector 0x1a4d01d2
    assert steps[0].transaction.data.startswith("0x1a4d01d2")


def test_remove_one_coin_min_dy_override():
    a = CurveSingleSidedAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="curve", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw", "pool_key": "3pool", "min_dy": 95_000_000},
    )
    steps = _run(a.build(req))
    body = steps[0].transaction.data[10:]
    # 3rd 32-byte word is min_dy
    min_dy_hex = body[2 * 64:3 * 64]
    assert int(min_dy_hex, 16) == 95_000_000


def test_remove_one_coin_actions_set():
    a = CurveSingleSidedAdapter()
    for action in ("remove_liquidity_one_coin", "withdraw"):
        assert a.supports(chain="ethereum", protocol="curve", action=action).supported
