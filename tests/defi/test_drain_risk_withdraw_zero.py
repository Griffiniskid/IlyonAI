"""Pin test for D-P1-14 drain-risk: withdraw(amount=0) was silently
rewritten to MAX_UINT256 across ERC-4626 vaults + Aave V3 native ETH
WTG3 withdraws.

Matrix Pass A wave 3 confirmed BOTH paths still drain-vulnerable:
  - D07 t2 Yearn ERC-4626 calldata `0xb460af94 ffff…ffff` + description
    "withdraw(0)"
  - D09 t2 Aave WTG3 native `withdrawETH(…, ffff…ffff, …)` + description
    "Withdraw 0 ETH"

User signing "0 withdraw" → contract drains entire position
(MAX_UINT256 is interpreted as "withdraw everything").

Fix: refuse amount_in==0 at the adapter unless explicit
extra.withdraw_all=true (in which case description correctly says
"Withdraw ALL" + calldata uses MAX_UINT256).
"""
from __future__ import annotations

import asyncio

import pytest

from src.defi.execution.adapters.erc4626 import ERC4626VaultAdapter
from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter


class _Req:
    """Minimal dummy build-request to avoid Pydantic envelope gymnastics."""
    def __init__(self, **kw):
        self.chain = kw.get("chain", "arbitrum")
        self.protocol = kw.get("protocol", "morpho-blue")
        self.action = kw.get("action", "supply")
        self.asset_in = kw.get("asset_in", "USDC")
        from decimal import Decimal
        self.amount_in = Decimal(str(kw.get("amount_in", "0")))
        self.user_address = kw.get("user_address", "0x" + "a" * 40)
        self.extra = kw.get("extra") or {}


def _run(coro):
    # Use a fresh loop per call so test order in a full suite run
    # doesn't accidentally close the loop.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── ERC-4626 ─────────────────────────────────────────────────────────────

def test_erc4626_withdraw_zero_refused_without_withdraw_all():
    adapter = ERC4626VaultAdapter()
    req = _Req(
        chain="arbitrum", protocol="morpho-blue", asset_in="USDC",
        amount_in="0",
        extra={"action": "withdraw", "curator": "gauntlet"},
    )
    with pytest.raises(ValueError, match="amount_in must be > 0"):
        _run(adapter.build(req))


def test_erc4626_withdraw_all_explicit_flag_passes():
    """When extra.withdraw_all=true, amount=0 is accepted and calldata
    correctly uses MAX_UINT256."""
    adapter = ERC4626VaultAdapter()
    req = _Req(
        chain="arbitrum", protocol="morpho-blue", asset_in="USDC",
        amount_in="0",
        extra={"action": "withdraw", "withdraw_all": True, "curator": "gauntlet"},
    )
    steps = _run(adapter.build(req))
    assert len(steps) == 1
    tx_data = steps[0].transaction.data
    assert tx_data.startswith("0xb460af94")
    assert "f" * 64 in tx_data.lower()
    assert "ALL" in steps[0].title or "ALL" in steps[0].description


def test_erc4626_withdraw_real_amount_works():
    adapter = ERC4626VaultAdapter()
    req = _Req(
        chain="arbitrum", protocol="morpho-blue", asset_in="USDC",
        amount_in="100",
        extra={"action": "withdraw", "curator": "gauntlet"},
    )
    steps = _run(adapter.build(req))
    assert len(steps) == 1
    assert "ALL" not in steps[0].title


# ─── Aave V3 native ETH withdraw via WTG3 ────────────────────────────────

def test_aave_native_withdraw_zero_refused_without_withdraw_all():
    adapter = AaveV3SupplyAdapter()
    req = _Req(
        chain="ethereum", protocol="aave-v3", asset_in="ETH",
        amount_in="0",
        extra={"action": "withdraw", "atoken_address": "0x" + "b" * 40},
    )
    with pytest.raises(ValueError, match="amount_in must be > 0"):
        _run(adapter.build(req))


def test_aave_native_withdraw_all_explicit_passes():
    adapter = AaveV3SupplyAdapter()
    req = _Req(
        chain="ethereum", protocol="aave-v3", asset_in="ETH",
        amount_in="0",
        extra={
            "action": "withdraw",
            "withdraw_all": True,
            "atoken_address": "0x4d5F47FA6A74757f35C14fD3a6Ef8E3C9BC514E8",
        },
    )
    steps = _run(adapter.build(req))
    assert len(steps) == 2
    withdraw_step = steps[1]
    assert withdraw_step.transaction.data.startswith("0x80500d20")
    assert "f" * 64 in withdraw_step.transaction.data.lower()
    assert "ALL" in withdraw_step.description
