"""V7-047 pin — 30s re-sim freshness window on the broadcast path.

Covers the exit criterion: `broadcast_step` MUST re-simulate the step
when its cached `simulated_at` is older than 30s (or missing entirely)
before the V7-010 bind invariant fires. Fresh steps (<= 30s) skip the
extra sim and rely on the cached hash.
"""
from __future__ import annotations

import time

import pytest

from src.defi.execution import broadcast as broadcast_mod
from src.defi.execution.broadcast import (
    SIM_FRESHNESS_THRESHOLD_SEC,
    _check_sim_freshness,
    broadcast_step,
)
from src.defi.execution.models import (
    ExecutionPlanV3,
    UnsignedStepTransaction,
    make_step,
)
from src.defi.simulator.tenderly_client import SimulationResult, TenderlyClient


class _StubTenderly(TenderlyClient):
    """Tenderly test double — skips HTTP, returns canned SimulationResults.

    Also tracks call count so the freshness gate can be asserted directly.
    """

    def __init__(self, *, result: SimulationResult) -> None:
        # Bypass parent __init__ to dodge api-key checks under pytest.
        self._result = result
        self.calls = 0

    async def simulate_bundle(self, transactions, network_id):  # type: ignore[override]
        self.calls += 1
        return self._result


def _plan_with_evm_step() -> ExecutionPlanV3:
    plan = ExecutionPlanV3.new(title="V7-047", summary="freshness test")
    step = make_step(
        index=0,
        action="swap",
        title="Swap",
        description="evm",
        chain="ethereum",
        wallet="MetaMask",
        protocol="enso",
        transaction=UnsignedStepTransaction(
            chain_kind="evm", chain_id=1,
            to="0xabc", data="0xdeadbeef", value="0",
        ),
    )
    plan.add_step(step)
    return plan


# ---------------------------------------------------------------------------
# _check_sim_freshness unit table
# ---------------------------------------------------------------------------


def test_check_sim_freshness_never_simulated_returns_false() -> None:
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    # Pre-condition: brand-new step has no sim hash + no timestamp.
    assert step.simulated_at is None
    assert step.simulated_calldata_hash is None
    assert _check_sim_freshness(step) is False


def test_check_sim_freshness_recent_sim_returns_true() -> None:
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    # Simulated 5 seconds ago — well within the 30s window.
    step.simulated_calldata_hash = "a" * 64
    step.simulated_at = time.time() - 5
    assert _check_sim_freshness(step) is True


def test_check_sim_freshness_stale_sim_returns_false() -> None:
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    # Simulated 35s ago — past the 30s window.
    step.simulated_calldata_hash = "a" * 64
    step.simulated_at = time.time() - 35
    assert _check_sim_freshness(step) is False


def test_check_sim_freshness_threshold_constant_is_30s() -> None:
    # The 30s freshness window is a spec contract; pin it.
    assert SIM_FRESHNESS_THRESHOLD_SEC == 30


# ---------------------------------------------------------------------------
# broadcast_step re-sim behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_step_fresh_sim_skips_resim_refresh() -> None:
    """Step simulated 5s ago: only the V7-010 pre-broadcast sim runs (1 call)."""
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    step.simulated_calldata_hash = "f" * 64
    step.simulated_at = time.time() - 5  # fresh

    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash="f" * 64, gas_used=50000,
    ))
    await broadcast_step(plan, step.step_id, tenderly=tenderly)

    # Only V7-010's mandatory pre-broadcast sim — no freshness refresh.
    assert tenderly.calls == 1
    assert step.status == "submitted"


@pytest.mark.asyncio
async def test_broadcast_step_stale_sim_triggers_resim() -> None:
    """Step simulated 35s ago: refresh sim + V7-010 sim = 2 calls."""
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    step.simulated_calldata_hash = "0" * 64
    step.simulated_at = time.time() - 35  # stale

    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash="b" * 64, gas_used=50000,
    ))
    await broadcast_step(plan, step.step_id, tenderly=tenderly)

    # Freshness refresh AND V7-010 pre-broadcast sim → simulator hit twice.
    assert tenderly.calls == 2
    # Fresh hash + timestamp now stamped from the latest sim.
    assert step.simulated_calldata_hash == "b" * 64
    assert step.simulated_at is not None
    assert (time.time() - step.simulated_at) < 5
    assert step.status == "submitted"


@pytest.mark.asyncio
async def test_broadcast_step_never_simulated_triggers_resim() -> None:
    """Step with no cached sim: refresh sim + V7-010 sim = 2 calls."""
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    assert step.simulated_at is None
    assert step.simulated_calldata_hash is None

    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash="c" * 64, gas_used=50000,
    ))
    await broadcast_step(plan, step.step_id, tenderly=tenderly)

    # Missing sim is treated as stale → refresh fires, then V7-010 sim.
    assert tenderly.calls == 2
    assert step.simulated_calldata_hash == "c" * 64
    assert step.simulated_at is not None
    assert step.status == "submitted"


@pytest.mark.asyncio
async def test_broadcast_step_resim_stamps_fresh_hash_and_timestamp() -> None:
    """The refresh sim MUST overwrite both the hash and the timestamp."""
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    # Stale stamp with an old hash; refresh must overwrite both.
    old_hash = "0" * 64
    old_ts = time.time() - 120
    step.simulated_calldata_hash = old_hash
    step.simulated_at = old_ts

    new_hash = "e" * 64
    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash=new_hash, gas_used=50000,
    ))
    t_before = time.time()
    await broadcast_step(plan, step.step_id, tenderly=tenderly)

    assert step.simulated_calldata_hash == new_hash
    assert step.simulated_calldata_hash != old_hash
    assert step.simulated_at is not None
    assert step.simulated_at >= t_before
    assert step.simulated_at != old_ts
