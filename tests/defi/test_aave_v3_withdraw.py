"""Aave V3 withdraw lifecycle — Pool.withdraw(asset, amount, to) selector."""
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


def test_withdraw_emits_pool_withdraw_call():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="base", protocol="aave-v3", asset_in="USDC", amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "withdraw"
    # Pool.withdraw(address,uint256,address) selector
    assert s.transaction.data.startswith("0x69328dec")
    # Pool address is the spender + to
    assert s.transaction.to.lower() == "0xa238dd80c259a72e81d7e4664a9801593f98d1c5"


def test_withdraw_with_zero_amount_means_max():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC", amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    steps = _run(a.build(req))
    data = steps[0].transaction.data
    # uint256.max embedded → all-FFs in the amount slot.
    assert "f" * 64 in data
    assert steps[0].description.endswith("returned.")


def test_withdraw_action_in_supported_set():
    a = AaveV3SupplyAdapter()
    r = a.supports(chain="ethereum", protocol="aave-v3", action="withdraw")
    assert r.supported is True
