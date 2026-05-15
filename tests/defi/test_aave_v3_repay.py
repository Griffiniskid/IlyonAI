"""Tests for Aave V3 repay lifecycle — Pool.repay selector."""
from __future__ import annotations

import asyncio
from decimal import Decimal

from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter
from src.defi.execution.adapters.base import YieldBuildRequest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_repay_emits_two_step_plan():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC",
        amount_in=Decimal("25"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "repay"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 2
    assert steps[0].action == "approve"
    assert steps[1].action == "repay"
    # Approve → Aave Pool (the spender for the repay).
    assert steps[0].transaction.data.startswith("0x095ea7b3")
    # Pool.repay(asset, amount, rateMode, onBehalfOf) selector
    assert steps[1].transaction.data.startswith("0x573ade81")


def test_repay_zero_amount_means_max():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "repay"},
    )
    steps = _run(a.build(req))
    # 2nd 32-byte field of repay payload is amount; should be all-FFs (max).
    body = steps[1].transaction.data[10:]
    amount_hex = body[64:128]
    assert int(amount_hex, 16) == (1 << 256) - 1


def test_repay_in_supported_actions():
    a = AaveV3SupplyAdapter()
    r = a.supports(chain="ethereum", protocol="aave-v3", action="repay")
    assert r.supported is True
