"""Tests for Uniswap V2 removeLiquidity withdraw branch.

Catches the same bug class as the Aave V3 borrow → supply mis-routing:
the adapter previously admitted action=withdraw but build() always emitted
addLiquidity. A user signing what they think is a withdraw would have
deposited instead.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.uniswap_v2 import UniswapV2DualTokenAdapter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _pcs_remove_request(**over) -> YieldBuildRequest:
    base = dict(
        chain="bsc",
        protocol="pancakeswap-v2",
        asset_in="WBNB",
        amount_in=Decimal("1"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        slippage_bps=100,
        extra={
            "action": "withdraw",
            "pool_address": "0xbbbb000000000000000000000000000000000000",
            "token_a": "WBNB",
            "token_b": "USDT",
        },
    )
    base.update(over)
    return YieldBuildRequest(**base)


def test_withdraw_emits_remove_liquidity_selector():
    a = UniswapV2DualTokenAdapter()
    steps = _run(a.build(_pcs_remove_request()))
    assert len(steps) == 2
    assert steps[0].action == "approve"
    assert steps[1].action == "remove_liquidity"
    # removeLiquidity selector
    assert steps[1].transaction.data.startswith("0xbaa2abde")


def test_withdraw_approves_lp_token_to_router():
    a = UniswapV2DualTokenAdapter()
    steps = _run(a.build(_pcs_remove_request()))
    approve = steps[0]
    # approve target is the LP pair address (token_a/token_b pair)
    assert approve.transaction.to.lower() == "0xbbbb000000000000000000000000000000000000"
    # spender encoded in the calldata is the router
    # PancakeSwap V2 router on BSC
    assert "10ed43c718714eb63d5aa57b78b54704e256024e" in approve.transaction.data.lower()


def test_withdraw_payload_is_7_words():
    """removeLiquidity(tokenA,tokenB,liquidity,amountAMin,amountBMin,to,deadline)
    has 7 × 32-byte words after the selector."""
    a = UniswapV2DualTokenAdapter()
    steps = _run(a.build(_pcs_remove_request()))
    body = steps[1].transaction.data[10:]
    assert len(body) == 7 * 64


def test_withdraw_rejects_missing_pool_address():
    a = UniswapV2DualTokenAdapter()
    req = _pcs_remove_request()
    req.extra.pop("pool_address")
    with pytest.raises(ValueError, match="extra.pool_address"):
        _run(a.build(req))


def test_withdraw_rejects_zero_liquidity():
    a = UniswapV2DualTokenAdapter()
    req = _pcs_remove_request(amount_in=Decimal("0"))
    with pytest.raises(ValueError, match="liquidity > 0"):
        _run(a.build(req))


def test_withdraw_action_routed_separately_from_deposit():
    """Regression pin: previously action=withdraw silently fell through to
    addLiquidity. After the fix, withdraw must produce removeLiquidity."""
    a = UniswapV2DualTokenAdapter()
    steps = _run(a.build(_pcs_remove_request()))
    # NOT addLiquidity selector
    assert not steps[1].transaction.data.startswith("0xe8e33700")


def test_deposit_still_emits_add_liquidity_regression_pin():
    """Make sure the new branch doesn't break the baseline deposit flow."""
    a = UniswapV2DualTokenAdapter()
    req = YieldBuildRequest(
        chain="bsc",
        protocol="pancakeswap-v2",
        asset_in="WBNB",
        amount_in=Decimal("1"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        slippage_bps=100,
        extra={"token_a": "WBNB", "token_b": "USDT", "amount_a": "1", "amount_b": "300"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 3
    assert steps[2].action == "add_liquidity"
    assert steps[2].transaction.data.startswith("0xe8e33700")
