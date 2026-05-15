"""Pending-plan registry — registers composed plans, resolves on webhook."""
from __future__ import annotations

import asyncio
import time

import pytest

from src.defi.execution.composed_plan import Snapshot
from src.defi.execution.models import (
    ExecutionPlanV3,
    UnsignedStepTransaction,
    make_step,
)
from src.defi.execution.pending_plans import (
    PendingPlan,
    clear_for_tests,
    drop,
    get,
    list_by_wallet,
    register,
    resolve_fill,
    size,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _snap() -> Snapshot:
    return Snapshot(
        bridge_name="debridge-dln", src_chain_id=1, dst_chain_id=8453,
        token_in="0xa", token_out="0xb",
        src_amount=100_000_000, expected_dst_amount=99_500_000,
        slippage_bps_band_min=0, slippage_bps_band_max=50,
        quote_id="q1", captured_at=time.time(),
    )


def _step():
    return make_step(
        index=2, action="supply",
        title="Cross-chain deposit",
        description="awaits bridge fill",
        chain="base", wallet="MetaMask", protocol="aave-v3",
        asset_in="USDC", amount_in="100", slippage_bps=50,
        gas_estimate_usd=2.0, duration_estimate_s=20,
        transaction=UnsignedStepTransaction(
            chain_kind="evm", chain_id=8453,
            to="0xa", data="0x", value="0x0", spender="0xa",
        ),
        status="blocked",
        blocker_codes=["PENDING_DST_FILL"],
    )


def _pending(plan_id: str = "plan-1", order_id: str = "order-abc") -> PendingPlan:
    return PendingPlan(
        plan_id=plan_id, order_id=order_id,
        plan=ExecutionPlanV3.new(title="t", summary="s"),
        deposit_step=_step(),
        snapshot=_snap(),
        user_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        src_chain="ethereum", dst_chain="base",
    )


def setup_function(_fn):
    clear_for_tests()


def test_register_increments_size():
    assert size() == 0
    _run(register(_pending()))
    assert size() == 1


def test_get_returns_registered():
    p = _pending()
    _run(register(p))
    found = _run(get(p.order_id))
    assert found is not None
    assert found.order_id == p.order_id


def test_get_unknown_returns_none():
    assert _run(get("not-an-order")) is None


def test_drop_removes_and_returns():
    p = _pending()
    _run(register(p))
    out = _run(drop(p.order_id))
    assert out is p
    assert _run(get(p.order_id)) is None


def test_list_by_wallet_filters():
    a = _pending("plan-a", "order-a")
    b = _pending("plan-b", "order-b")
    b.user_wallet = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    _run(register(a))
    _run(register(b))
    a_only = _run(list_by_wallet("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
    assert len(a_only) == 1


def test_resolve_fill_filled_promotes_step():
    p = _pending()
    _run(register(p))
    payload = _run(resolve_fill(
        p.order_id, actual_dst_amount=99_700_000, state="filled",
    ))
    assert payload is not None
    assert payload["kind"] == "bridge_resolution"
    assert payload["state"] == "filled"
    assert p.deposit_step.status == "ready"
    assert "PENDING_DST_FILL" not in p.deposit_step.blocker_codes
    # Entry dropped after fill
    assert _run(get(p.order_id)) is None


def test_resolve_fill_failed_keeps_blocker():
    p = _pending()
    _run(register(p))
    payload = _run(resolve_fill(
        p.order_id, actual_dst_amount=None, state="failed",
    ))
    assert payload is not None
    assert payload["state"] == "failed"
    assert p.deposit_step.status == "blocked"
    assert "PENDING_DST_FILL" in p.deposit_step.blocker_codes


def test_resolve_fill_unknown_order_returns_none():
    out = _run(resolve_fill("not-an-order", actual_dst_amount=1, state="filled"))
    assert out is None


def test_resolve_fill_cancelled_drops_entry():
    p = _pending()
    _run(register(p))
    _run(resolve_fill(p.order_id, actual_dst_amount=None, state="cancelled"))
    assert size() == 0
