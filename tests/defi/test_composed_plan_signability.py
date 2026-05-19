"""RC7a — composed_plan signability invariant pin tests.

Pin: refuse plan emission when any non-blocked step has `transaction is None`.
Pass A H04/H05/H06 leaked composed-plan cards where the deBridge bridge step
carried `transaction:null` while reading as `status:"ready"`. Clicking sign
would noop or skip ahead — a financial-loss bug. These tests pin the
`assert_signable_composed_plan` invariant.
"""
from __future__ import annotations

import pytest

from src.defi.execution.composed_plan import (
    ComposedPlanIncompleteTxError,
    assert_signable_composed_plan,
    block_step_for_async_fill,
)
from src.defi.execution.models import (
    ExecutionPlanV3,
    ExecutionStepV3,
    UnsignedStepTransaction,
    make_step,
)


def _step(*, index: int, action: str = "supply", with_tx: bool = True,
          status: str = "pending") -> ExecutionStepV3:
    tx = UnsignedStepTransaction(
        chain_kind="evm", chain_id=1,
        to="0x" + "11" * 20, data="0xdeadbeef", value="0x0",
    ) if with_tx else None
    return make_step(
        index=index, action=action, title=f"step {index}",
        description="test", chain="ethereum", wallet="MetaMask",
        protocol="aave-v3", asset_in="USDC", amount_in="100",
        transaction=tx,
    )


def test_signable_plan_passes_invariant():
    """Two-step plan where every step has a transaction must pass."""
    plan = ExecutionPlanV3.new(title="ok plan", summary="all signable")
    plan.steps = [_step(index=1, action="approve"), _step(index=2)]
    # Must not raise.
    assert_signable_composed_plan(plan)


def test_bridge_step_without_tx_is_refused():
    """RC7a — bridge step with transaction=None and status=pending: REFUSE."""
    plan = ExecutionPlanV3.new(title="bad plan", summary="bridge has no calldata")
    bridge = _step(index=1, action="bridge", with_tx=False, status="pending")
    deposit = _step(index=2, action="supply")
    plan.steps = [bridge, deposit]
    with pytest.raises(ComposedPlanIncompleteTxError) as exc_info:
        assert_signable_composed_plan(plan)
    assert exc_info.value.step_index == 1
    assert exc_info.value.action == "bridge"


def test_blocked_step_without_tx_is_allowed():
    """A step that is BLOCKED on PENDING_DST_FILL doesn't need a tx yet —
    the runtime rebuilds it after the upstream bridge fills."""
    plan = ExecutionPlanV3.new(title="composed", summary="blocked step ok")
    bridge = _step(index=1, action="bridge", with_tx=True)
    deposit = _step(index=2, action="supply", with_tx=False)
    block_step_for_async_fill(deposit, blocker_code="PENDING_DST_FILL")
    plan.steps = [bridge, deposit]
    # Must not raise — blocked step is exempt.
    assert_signable_composed_plan(plan)


def test_invariant_error_surface_carries_step_metadata():
    """The error carries step_index + step_id + action so the emitter can
    convert it into a COMPOSED_PLAN_INCOMPLETE_TX blocker."""
    plan = ExecutionPlanV3.new(title="x", summary="x")
    s = _step(index=3, action="supply", with_tx=False, status="pending")
    plan.steps = [s]
    with pytest.raises(ComposedPlanIncompleteTxError) as exc_info:
        assert_signable_composed_plan(plan)
    e = exc_info.value
    assert e.step_index == 3
    assert e.step_id.startswith("step_")
    assert e.action == "supply"
    # Stringification includes all three for log readability.
    s_str = str(e)
    assert "index=3" in s_str
    assert "transaction=None" in s_str
