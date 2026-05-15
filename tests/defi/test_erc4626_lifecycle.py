"""Tests for ERC-4626 withdraw + redeem lifecycle (Yearn, Morpho, Spark, Lido, etc.)."""
from __future__ import annotations

import asyncio
from decimal import Decimal

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.erc4626 import ERC4626VaultAdapter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_withdraw_selector_b460af94():
    a = ERC4626VaultAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="yearn", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "withdraw"
    assert s.transaction.data.startswith("0xb460af94")


def test_redeem_selector_ba087652():
    a = ERC4626VaultAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="morpho-blue", asset_in="USDC",
        amount_in=Decimal("50"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "redeem"},
    )
    steps = _run(a.build(req))
    assert steps[0].action == "redeem"
    assert steps[0].transaction.data.startswith("0xba087652")


def test_zero_amount_means_max():
    a = ERC4626VaultAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="yearn", asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    steps = _run(a.build(req))
    body = steps[0].transaction.data[10:]
    # 1st 32-byte field is shares/assets — should be uint256.max sentinel.
    amount_hex = body[:64]
    assert int(amount_hex, 16) == (1 << 256) - 1


def test_withdraw_redeem_in_supported_actions():
    a = ERC4626VaultAdapter()
    for action in ("withdraw", "redeem"):
        assert a.supports(chain="ethereum", protocol="yearn", action=action).supported
