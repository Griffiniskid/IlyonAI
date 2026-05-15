"""Tests for Aave V3 borrow lifecycle — Pool.borrow selector."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter
from src.defi.execution.adapters.base import YieldBuildRequest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_borrow_emits_pool_borrow_call():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="base", protocol="aave-v3", asset_in="USDC", amount_in=Decimal("50"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "borrow"
    # Pool.borrow(asset, amount, rateMode, referralCode, onBehalfOf) selector
    assert s.transaction.data.startswith("0xa415bcad")
    # Aave V3 Pool on Base
    assert s.transaction.to.lower() == "0xa238dd80c259a72e81d7e4664a9801593f98d1c5"
    # 5 32-byte fields after the 4-byte selector
    body = s.transaction.data[10:]
    assert len(body) == 5 * 64


def test_borrow_rate_mode_defaults_to_variable():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC", amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    steps = _run(a.build(req))
    body = steps[0].transaction.data[10:]
    # 3rd 32-byte field is interestRateMode (default variable = 2).
    rate_mode_hex = body[2 * 64:3 * 64]
    assert int(rate_mode_hex, 16) == 2


def test_borrow_rate_mode_override():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC", amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow", "rate_mode": 1},  # stable
    )
    steps = _run(a.build(req))
    body = steps[0].transaction.data[10:]
    rate_mode_hex = body[2 * 64:3 * 64]
    assert int(rate_mode_hex, 16) == 1


def test_borrow_rejects_zero_amount():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC", amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError, match="Borrow amount must be > 0"):
            loop.run_until_complete(a.build(req))
    finally:
        loop.close()


def test_borrow_in_supported_actions():
    a = AaveV3SupplyAdapter()
    r = a.supports(chain="ethereum", protocol="aave-v3", action="borrow")
    assert r.supported is True


def test_borrow_no_approve_step():
    """Critical: borrow MUST NOT include an ERC20 approve step. Borrow
    mints debt; it doesn't pull funds from the user wallet. Including an
    approve would be a footgun.
    """
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC", amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "borrow"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert steps[0].action == "borrow"
    # No approve sub-step.
    assert not any("approve" in (s.action or "") for s in steps if s != steps[0])
