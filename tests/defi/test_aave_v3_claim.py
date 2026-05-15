"""Tests for Aave V3 claim — RewardsController.claimAllRewards selector."""
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


def test_claim_emits_rewards_controller_call():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="base", protocol="aave-v3", asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "claim"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "claim"
    # RewardsController.claimAllRewards selector
    assert s.transaction.data.startswith("0xbb492bf5")
    # Base chain RewardsController
    assert s.transaction.to.lower() == "0xf9cc4f0d883f1a1eb2c253bdb46c254ca51e1f44"


def test_claim_chain_specific_address():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "claim"},
    )
    steps = _run(a.build(req))
    # Ethereum RewardsController
    assert steps[0].transaction.to.lower() == "0x8164cc65827dcfe994ab23944cbc90e0aa80bfcb"


def test_claim_in_supported_actions():
    a = AaveV3SupplyAdapter()
    r = a.supports(chain="ethereum", protocol="aave-v3", action="claim")
    assert r.supported is True
