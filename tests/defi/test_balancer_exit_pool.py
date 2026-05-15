"""Tests for Balancer exitPool withdraw branch.

Same bug class as Aave V3 borrow→supply and V2 withdraw→addLiquidity:
the adapter admitted action=exit_pool but build() always emitted joinPool.
A user signing what they think is an exit would have re-deposited.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.balancer import (
    BalancerSingleAssetAdapter,
    _bpt_address_from_pool_id,
    _encode_exit_user_data_single,
)
from src.defi.execution.adapters.base import YieldBuildRequest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _exit_request(**over) -> YieldBuildRequest:
    base = dict(
        chain="ethereum",
        protocol="balancer-v2",
        asset_in="wstETH",
        amount_in=Decimal("0.5"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        slippage_bps=100,
        extra={
            "action": "exit_pool",
            "pool_key": "wsteth-weth",
            "exit_token": "wstETH",
        },
    )
    base.update(over)
    return YieldBuildRequest(**base)


def test_bpt_address_extracted_from_pool_id():
    pool_id = "0x32296969ef14eb0c6d29669c550d4a0449130230000200000000000000000080"
    # First 20 bytes (40 hex chars) of poolId = BPT contract address.
    assert _bpt_address_from_pool_id(pool_id) == "0x32296969ef14eb0c6d29669c550d4a0449130230"


def test_bpt_address_correct_length():
    pool_id = "0x32296969ef14eb0c6d29669c550d4a0449130230000200000000000000000080"
    addr = _bpt_address_from_pool_id(pool_id)
    assert addr.startswith("0x")
    assert len(addr) == 42


def test_exit_user_data_kind_zero():
    """userData for EXACT_BPT_IN_FOR_ONE_TOKEN_OUT has kind=0 in first 32 bytes."""
    ud = _encode_exit_user_data_single(bpt_in=10**18, exit_token_index=1)
    # First 32 bytes are uint256 kind = 0
    assert ud[:32] == b"\x00" * 32
    # Next 32 bytes are bpt_in = 10**18 = 0xde0b6b3a7640000
    assert int.from_bytes(ud[32:64], "big") == 10**18
    # Next 32 bytes are exit_token_index = 1
    assert int.from_bytes(ud[64:96], "big") == 1


def test_exit_emits_exitpool_selector():
    a = BalancerSingleAssetAdapter()
    steps = _run(a.build(_exit_request()))
    assert len(steps) == 2
    assert steps[0].action == "approve"
    assert steps[1].action == "exit_pool"
    # exitPool selector
    assert steps[1].transaction.data.startswith("0x8bdb3913")


def test_exit_not_joinpool_regression():
    """Critical regression pin: must NOT emit joinPool selector 0xb95cac28."""
    a = BalancerSingleAssetAdapter()
    steps = _run(a.build(_exit_request()))
    assert not steps[1].transaction.data.startswith("0xb95cac28")


def test_exit_approve_targets_bpt_to_vault():
    a = BalancerSingleAssetAdapter()
    steps = _run(a.build(_exit_request()))
    approve = steps[0]
    # approve target: BPT (= high 20 bytes of poolId for wsteth-weth)
    assert approve.transaction.to.lower() == "0x32296969ef14eb0c6d29669c550d4a0449130230"
    # spender = Vault
    assert "ba12222222228d8ba445958a75a0704d566bf2c8" in approve.transaction.data.lower()


def test_exit_rejects_zero_bpt():
    a = BalancerSingleAssetAdapter()
    with pytest.raises(ValueError, match="BPT amount > 0"):
        _run(a.build(_exit_request(amount_in=Decimal("0"))))


def test_exit_rejects_unknown_exit_token():
    a = BalancerSingleAssetAdapter()
    req = _exit_request()
    req.extra["exit_token"] = "DAI"  # not in wsteth-weth pool
    with pytest.raises(ValueError, match="doesn't contain DAI"):
        _run(a.build(req))


def test_join_still_emits_joinpool_regression_pin():
    """Make sure the new branch doesn't break the baseline deposit flow."""
    a = BalancerSingleAssetAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="balancer-v2",
        asset_in="wstETH",
        amount_in=Decimal("0.5"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        slippage_bps=100,
        extra={"pool_key": "wsteth-weth"},
    )
    steps = _run(a.build(req))
    assert steps[1].action == "join_pool"
    assert steps[1].transaction.data.startswith("0xb95cac28")
