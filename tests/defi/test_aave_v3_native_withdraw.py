"""Aave V3 native ETH withdraw via WrappedTokenGatewayV3.withdrawETH 0x80500d20."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.aave_v3 import (
    AaveV3SupplyAdapter,
    _AAVE_POOL_ADDRESSES,
    _AAVE_WTG3_ADDRESSES,
)
from src.defi.execution.adapters.base import YieldBuildRequest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _native_withdraw_req(chain="ethereum", amount="0.05"):
    return YieldBuildRequest(
        chain=chain, protocol="aave-v3", asset_in="ETH",
        amount_in=Decimal(amount),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={
            "action": "withdraw",
            "atoken_address": "0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8",  # aWETH ethereum
        },
    )


def test_native_eth_withdraw_emits_wtg3_withdrawETH():
    a = AaveV3SupplyAdapter()
    steps = _run(a.build(_native_withdraw_req()))
    assert len(steps) == 2
    assert steps[0].action == "approve"
    assert steps[1].action == "withdraw"
    # withdrawETH selector
    assert steps[1].transaction.data.startswith("0x80500d20")


def test_native_eth_withdraw_targets_wtg3():
    a = AaveV3SupplyAdapter()
    steps = _run(a.build(_native_withdraw_req()))
    assert steps[1].transaction.to == _AAVE_WTG3_ADDRESSES["ethereum"]


def test_native_eth_withdraw_approve_targets_atoken():
    """Approval must be to the aToken, not the underlying."""
    a = AaveV3SupplyAdapter()
    steps = _run(a.build(_native_withdraw_req()))
    assert steps[0].transaction.to.lower() == "0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8"
    # spender = WTG3
    assert _AAVE_WTG3_ADDRESSES["ethereum"].lower()[2:] in steps[0].transaction.data.lower()


def test_native_eth_withdraw_payload_shape():
    """withdrawETH(pool, amount, to) — 3 words after selector."""
    a = AaveV3SupplyAdapter()
    steps = _run(a.build(_native_withdraw_req()))
    body = steps[1].transaction.data[10:]
    assert len(body) == 3 * 64


def test_native_eth_withdraw_encodes_pool_address():
    a = AaveV3SupplyAdapter()
    steps = _run(a.build(_native_withdraw_req()))
    body = steps[1].transaction.data[10:].lower()
    pool = _AAVE_POOL_ADDRESSES["ethereum"][2:].lower()
    assert body[24:64] == pool


def test_native_withdraw_zero_amount_uses_max_sentinel():
    """amount=0 → uint256.max for withdraw all aWETH."""
    a = AaveV3SupplyAdapter()
    steps = _run(a.build(_native_withdraw_req(amount="0")))
    data = steps[1].transaction.data
    assert "f" * 64 in data


def test_native_withdraw_falls_back_to_registry_atoken():
    """When extra.atoken_address absent, adapter consults its per-chain
    registry instead of raising — fix landed after live SSE caught
    'extra.atoken_address' raise blocking the user."""
    a = AaveV3SupplyAdapter()
    req = _native_withdraw_req()
    req.extra.pop("atoken_address")
    steps = _run(a.build(req))
    # Auto-resolved to canonical aWETH on Ethereum
    assert steps[0].transaction.to.lower() == "0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8"


def test_native_withdraw_on_unsupported_chain_raises():
    """Chain without an aToken registry entry should still raise."""
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="avalanche", protocol="aave-v3", asset_in="AVAX",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    # WTG3 not registered for avalanche → ValueError
    with pytest.raises(ValueError, match="WrappedTokenGatewayV3 not registered"):
        _run(a.build(req))


def test_erc20_withdraw_baseline_still_works():
    """Non-native withdraw must still hit Pool.withdraw 0x69328dec."""
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert steps[0].transaction.data.startswith("0x69328dec")
