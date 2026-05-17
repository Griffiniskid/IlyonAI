"""V7-010 wire-in pin — sim runs BEFORE V7-001 bind invariant fires.

Covers the exit criterion: `simulated_calldata_hash` is populated by the
simulator BEFORE `mark_step_status('submitted')` is invoked, so the
V7-001 bind invariant has a hash to compare against.
"""
from __future__ import annotations

import pytest

from src.defi.execution.broadcast import (
    BroadcastSimulationError,
    broadcast_step,
)
from src.defi.execution.models import (
    ExecutionPlanV3,
    UnsignedStepTransaction,
    make_step,
)
from src.defi.simulator.tenderly_client import SimulationResult, TenderlyClient


class _StubTenderly(TenderlyClient):
    """Test double that skips HTTP and returns a canned SimulationResult."""

    def __init__(self, *, result: SimulationResult) -> None:
        # Bypass parent __init__ to avoid api-key checks in tests.
        self._result = result

    async def simulate_bundle(self, transactions, network_id):  # type: ignore[override]
        return self._result


def _plan_with_evm_step() -> ExecutionPlanV3:
    plan = ExecutionPlanV3.new(title="V7-010", summary="wire test")
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


@pytest.mark.asyncio
async def test_broadcast_step_stamps_sim_hash_before_submit_flip() -> None:
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    assert step.simulated_calldata_hash is None  # pre-condition

    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash="f" * 64, gas_used=50000,
    ))
    await broadcast_step(plan, step.step_id, tenderly=tenderly)

    # Hash stamped + step flipped → bind invariant passed.
    assert step.simulated_calldata_hash == "f" * 64
    assert step.broadcast_calldata_hash == "f" * 64
    assert step.status == "submitted"


@pytest.mark.asyncio
async def test_broadcast_step_raises_on_sim_failure_and_does_not_flip() -> None:
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    tenderly = _StubTenderly(result=SimulationResult(
        success=False, calldata_hash="0" * 64,
        error_message="execution reverted: bad allowance",
    ))

    with pytest.raises(BroadcastSimulationError) as exc:
        await broadcast_step(plan, step.step_id, tenderly=tenderly)

    assert "bad allowance" in str(exc.value)
    # Step is NOT flipped to submitted on sim failure.
    assert step.status != "submitted"
    # And the hash is NOT stamped — we never bind to a failed sim.
    assert step.simulated_calldata_hash is None


@pytest.mark.asyncio
async def test_broadcast_step_raises_when_evm_tenderly_not_configured() -> None:
    plan = _plan_with_evm_step()
    step = plan.steps[0]
    with pytest.raises(BroadcastSimulationError):
        await broadcast_step(plan, step.step_id, tenderly=None)
    assert step.status != "submitted"


@pytest.mark.asyncio
async def test_broadcast_step_dispatches_to_solana_for_solana_chain_kind(monkeypatch) -> None:
    plan = ExecutionPlanV3.new(title="V7-010 sol", summary="wire test")
    step = make_step(
        index=0,
        action="swap",
        title="Swap",
        description="solana",
        chain="solana",
        wallet="Phantom",
        protocol="jupiter",
        transaction=UnsignedStepTransaction(
            chain_kind="solana", serialized="AbCdEf=="
        ),
    )
    plan.add_step(step)

    captured = {}

    async def fake_simulate_transaction(rpc_url, serialized_tx_b64, **kw):
        captured["rpc_url"] = rpc_url
        captured["tx"] = serialized_tx_b64
        return SimulationResult(
            success=True, calldata_hash="a" * 64, compute_units=10_000,
        )

    monkeypatch.setattr(
        "src.defi.execution.broadcast.simulate_transaction",
        fake_simulate_transaction,
    )

    await broadcast_step(
        plan, step.step_id, solana_rpc_url="https://rpc.example",
    )
    assert captured["rpc_url"] == "https://rpc.example"
    assert captured["tx"] == "AbCdEf=="
    assert step.simulated_calldata_hash == "a" * 64
    assert step.status == "submitted"
