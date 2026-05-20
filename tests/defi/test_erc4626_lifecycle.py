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


def test_zero_amount_requires_explicit_withdraw_all():
    """Matrix Pass A wave 3 D-P1-14 drain-risk fix.

    Pre-fix: amount_in=0 silently rewrote to MAX_UINT256 while
    description still read "withdraw(0)". User signing "0 withdraw"
    would drain entire position.

    Post-fix: amount_in=0 raises ValueError unless extra.withdraw_all
    is explicitly true (in which case description correctly says
    "Withdraw ALL" + calldata uses MAX_UINT256).
    """
    import pytest
    a = ERC4626VaultAdapter()
    # Bare zero amount must refuse — silent drain-rewrite removed.
    req_bare_zero = YieldBuildRequest(
        chain="ethereum", protocol="yearn", asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    with pytest.raises(ValueError, match="amount_in must be > 0"):
        _run(a.build(req_bare_zero))

    # Explicit withdraw_all=true accepts amount_in=0 and uses MAX_UINT256
    # with a description that calls it out clearly.
    req_explicit = YieldBuildRequest(
        chain="ethereum", protocol="yearn", asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw", "withdraw_all": True},
    )
    steps = _run(a.build(req_explicit))
    body = steps[0].transaction.data[10:]
    amount_hex = body[:64]
    assert int(amount_hex, 16) == (1 << 256) - 1
    assert "ALL" in steps[0].title or "ALL" in steps[0].description


def test_withdraw_redeem_in_supported_actions():
    a = ERC4626VaultAdapter()
    for action in ("withdraw", "redeem"):
        assert a.supports(chain="ethereum", protocol="yearn", action=action).supported
