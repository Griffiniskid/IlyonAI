"""Aave V3 native ETH borrow via WrappedTokenGatewayV3.borrowETH (0x66514c97).

Two steps:
  1. variableDebtWETH.approveDelegation(WTG3, amount) → 0xc04a8a10
  2. WTG3.borrowETH(pool, amount, rateMode, referralCode) → 0x66514c97
"""
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


def test_native_borrow_emits_approve_delegation_then_borrow_eth():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 2
    s1, s2 = steps

    # Step 1: approveDelegation on variableDebtWETH (Ethereum)
    assert s1.action == "approve"
    assert s1.transaction.data.startswith("0xc04a8a10")
    assert s1.transaction.to.lower() == "0xea51d7853eefb32b6ee06b1c12e6dcca88be0ffe"
    assert s1.transaction.spender.lower() == "0xd322a49006fc828f9b5b37ab215f99b4e5cab19c"

    # Step 2: borrowETH on WTG3
    assert s2.action == "borrow"
    assert s2.transaction.data.startswith("0x66514c97")
    assert s2.transaction.to.lower() == "0xd322a49006fc828f9b5b37ab215f99b4e5cab19c"
    assert s2.asset_out == "ETH"


def test_native_borrow_base_chain():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="base", protocol="aave-v3", asset_in="ETH",
        amount_in=Decimal("0.1"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 2
    s1, s2 = steps
    # variableDebtWETH on Base
    assert s1.transaction.to.lower() == "0x24e6e0795b3c7c71d965fcc4f371803d1c1dca1e"
    # WTG3 on Base
    assert s2.transaction.to.lower() == "0x729b3ea8c005abc58c9150fb57ec161296f06766"
    # Selectors
    assert s1.transaction.data.startswith("0xc04a8a10")
    assert s2.transaction.data.startswith("0x66514c97")


def test_erc20_borrow_still_works():
    """Regression pin: non-native borrow path remains single-step Pool.borrow."""
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="base", protocol="aave-v3", asset_in="USDC",
        amount_in=Decimal("50"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "borrow"
    assert s.transaction.data.startswith("0xa415bcad")
