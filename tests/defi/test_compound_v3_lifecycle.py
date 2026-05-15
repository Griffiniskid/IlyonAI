"""Tests for Compound v3 lifecycle — withdraw + borrow + claim."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.compound_v3 import CompoundV3SupplyAdapter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_withdraw_selector():
    a = CompoundV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="compound-v3", asset_in="USDC",
        amount_in=Decimal("50"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert steps[0].action == "withdraw"
    # Comet.withdraw selector
    assert steps[0].transaction.data.startswith("0xf3fef3a3")


def test_borrow_uses_same_selector_as_withdraw():
    """Compound v3 borrow = Comet.withdraw on base asset against collateral."""
    a = CompoundV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="compound-v3", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    steps = _run(a.build(req))
    assert steps[0].action == "borrow"
    assert steps[0].transaction.data.startswith("0xf3fef3a3")
    # Description mentions loan / borrow semantics so user isn't confused.
    desc = steps[0].description.lower()
    assert "borrow" in desc or "loan" in desc


def test_borrow_rejects_zero_amount():
    a = CompoundV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="compound-v3", asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError, match="Borrow amount must be > 0"):
            loop.run_until_complete(a.build(req))
    finally:
        loop.close()


def test_claim_routes_to_comet_rewards():
    a = CompoundV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="compound-v3", asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "claim"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert steps[0].action == "claim"
    # CometRewards.claim selector
    assert steps[0].transaction.data.startswith("0xb7034f7e")
    # Ethereum CometRewards
    assert steps[0].transaction.to.lower() == "0x1b0e765f6224c21223aea2af16c1c46e38885a40"


def test_actions_include_borrow_claim_withdraw():
    a = CompoundV3SupplyAdapter()
    for action in ("supply", "withdraw", "borrow", "claim"):
        assert a.supports(chain="ethereum", protocol="compound-v3", action=action).supported
