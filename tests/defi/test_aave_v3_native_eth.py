"""Aave V3 native ETH supply via WrappedTokenGatewayV3 — selector 0x474cf53d."""
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


def test_eth_supply_emits_wtg3_depositETH():
    """Native ETH supply routes to WrappedTokenGatewayV3.depositETH (no approve)."""
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    # 1 step only — no ERC20 approve needed for native deposit.
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "supply"
    # depositETH selector 0x474cf53d
    assert s.transaction.data.startswith("0x474cf53d")


def test_eth_supply_targets_wtg3_contract():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    # Target = WTG3 on Ethereum (not Pool directly)
    assert steps[0].transaction.to == _AAVE_WTG3_ADDRESSES["ethereum"]


def test_eth_supply_value_carries_amount_in_wei():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    # 0.05 ETH = 5 * 10^16 wei = 0xb1a2bc2ec50000
    assert steps[0].transaction.value == "0xb1a2bc2ec50000"


def test_eth_supply_payload_3_words_after_selector():
    """depositETH(address pool, address onBehalfOf, uint16 referralCode) = 3 words."""
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    body = steps[0].transaction.data[10:]
    assert len(body) == 3 * 64


def test_eth_supply_encodes_pool_address_in_first_arg():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    body = steps[0].transaction.data[10:].lower()
    # First 32-byte word = Pool address (left-padded)
    pool_lower = _AAVE_POOL_ADDRESSES["ethereum"][2:].lower()
    assert body[24:64] == pool_lower


def test_native_supply_chains():
    """Each supported chain has both a Pool and a WTG3 entry."""
    for chain in ("ethereum", "polygon", "arbitrum", "optimism", "base"):
        assert chain in _AAVE_POOL_ADDRESSES
        assert chain in _AAVE_WTG3_ADDRESSES


def test_matic_native_supply_routes_to_wtg3_on_polygon():
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="polygon", protocol="aave-v3", asset_in="MATIC",
        amount_in=Decimal("10"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert steps[0].transaction.data.startswith("0x474cf53d")
    assert steps[0].transaction.to == _AAVE_WTG3_ADDRESSES["polygon"]


def test_eth_native_branch_skipped_for_withdraw_action():
    """Lifecycle withdraw must not be redirected to WTG3 deposit."""
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="WETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    steps = _run(a.build(req))
    # Pool.withdraw selector 0x69328dec — not WTG3.depositETH
    assert steps[0].transaction.data.startswith("0x69328dec")


def test_erc20_supply_baseline_unaffected_regression_pin():
    """Non-native USDC supply must still go through ERC20 approve + Pool.supply."""
    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="aave-v3", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    assert len(steps) == 2
    assert steps[0].action == "approve"
    assert steps[0].transaction.data.startswith("0x095ea7b3")
    assert steps[1].action == "supply"
    # Pool.supply selector 0x617ba037
    assert steps[1].transaction.data.startswith("0x617ba037")
