"""rekey on bridge confirmation."""
from __future__ import annotations

import asyncio
import time

from src.defi.execution.composed_plan import Snapshot
from src.defi.execution.models import (
    ExecutionPlanV3,
    UnsignedStepTransaction,
    make_step,
)
from src.defi.execution.pending_plans import (
    PendingPlan,
    clear_for_tests,
    get,
    register,
    rekey,
    resolve_fill,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _pending(order_id: str = "quote-1") -> PendingPlan:
    return PendingPlan(
        plan_id="plan-x", order_id=order_id,
        plan=ExecutionPlanV3.new(title="t", summary="s"),
        deposit_step=make_step(
            index=2, action="supply", title="t", description="d",
            chain="base", wallet="MetaMask", protocol="aave-v3",
            asset_in="USDC", amount_in="100",
            slippage_bps=50, gas_estimate_usd=2.0, duration_estimate_s=20,
            transaction=UnsignedStepTransaction(
                chain_kind="evm", chain_id=8453,
                to="0xa", data="0x", value="0x0", spender="0xa",
            ),
            status="blocked", blocker_codes=["PENDING_DST_FILL"],
        ),
        snapshot=Snapshot(
            bridge_name="debridge-dln", src_chain_id=1, dst_chain_id=8453,
            token_in="0xa", token_out="0xb",
            src_amount=100_000_000, expected_dst_amount=99_500_000,
            slippage_bps_band_min=0, slippage_bps_band_max=50,
            quote_id=order_id, captured_at=time.time(),
        ),
        user_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        src_chain="ethereum", dst_chain="base",
    )


def setup_function(_fn):
    clear_for_tests()


def test_rekey_swaps_order_id():
    p = _pending("quote-old")
    _run(register(p))
    out = _run(rekey("quote-old", "real-new"))
    assert out is not None
    assert out.order_id == "real-new"
    assert _run(get("quote-old")) is None
    assert _run(get("real-new")) is not None


def test_rekey_returns_none_for_unknown():
    assert _run(rekey("nope", "real")) is None


def test_resolve_fill_works_after_rekey():
    p = _pending("quote-old")
    _run(register(p))
    _run(rekey("quote-old", "real-id"))
    payload = _run(resolve_fill("real-id", actual_dst_amount=99_500_000, state="filled"))
    assert payload is not None
    assert payload["state"] == "filled"
    assert p.deposit_step.status == "ready"
