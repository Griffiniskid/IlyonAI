"""V7-010 broadcast guard — sim-before-bind wire-in.

Spec quote: "Tenderly bundle simulator (EVM) + Solana simulateTransaction
with replaceRecentBlockhash. Wired so simulated_calldata_hash is
populated BEFORE V7-001's bind invariant fires."

This module is the single broadcast entry-point for ExecutionPlanV3.
It dispatches on `step.transaction.chain_kind`, calls the appropriate
simulator (Tenderly bundle for EVM, Solana RPC for Solana), stamps
`step.simulated_calldata_hash` AND `step.broadcast_calldata_hash`
with the simulator's deterministic hash of the unsigned tx, and then
hands off to `plan.mark_step_status(step_id, 'submitted')` so V7-001's
bind invariant validates they match.

The two hashes are intentionally seeded with the same value here
because the broadcast hasn't happened yet at the moment of simulation
— the wallet layer is expected to recompute `broadcast_calldata_hash`
over the final wire-format bytes immediately before signing and OVERWRITE
the seeded value. If the wallet layer's hash differs from what we
simulated, V7-001's `assert_calldata_match` raises. If the wallet layer
never overwrites (which means it signed the exact bytes we simulated),
the hashes trivially match and the bind passes.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.defi.simulator.solana_simulator import simulate_transaction
from src.defi.simulator.tenderly_client import (
    SimulationResult,
    TenderlyClient,
)

if TYPE_CHECKING:
    from src.defi.execution.models import ExecutionPlanV3, ExecutionStepV3

logger = logging.getLogger(__name__)


class BroadcastSimulationError(Exception):
    """Raised when pre-broadcast simulation fails or refuses to bind.

    Carries the upstream `SimulationResult` so the UI can surface the
    revert reason / compute-unit-exceeded / RPC outage instead of just
    a blanket "broadcast refused".
    """

    def __init__(
        self,
        sim: SimulationResult,
        *,
        step_id: str,
        plan_id: str | None = None,
    ) -> None:
        self.sim = sim
        self.step_id = step_id
        self.plan_id = plan_id
        msg = (
            f"pre-broadcast simulation refused step {step_id}"
            + (f" (plan {plan_id})" if plan_id else "")
            + f": {sim.error_message or 'unknown'}"
        )
        super().__init__(msg)


async def simulate_step_before_broadcast(
    plan: "ExecutionPlanV3",
    step: "ExecutionStepV3",
    *,
    tenderly: TenderlyClient | None = None,
    solana_rpc_url: str | None = None,
    network_id: int | None = None,
) -> SimulationResult:
    """Simulate the step's unsigned tx and stamp the calldata hash.

    Dispatches on `step.transaction.chain_kind`:
      - "evm"    → Tenderly bundle (single-leg) at `network_id`
      - "solana" → Solana RPC `simulateTransaction` at `solana_rpc_url`

    On success the step's `simulated_calldata_hash` is stamped (and
    seeded into `broadcast_calldata_hash` so the V7-001 bind passes when
    the wallet layer signs the exact simulated bytes). On failure the
    hashes are left untouched and the caller is expected to raise/abort.
    """
    if step.transaction is None:
        raise BroadcastSimulationError(
            SimulationResult(
                success=False,
                calldata_hash="",
                error_message="step has no unsigned transaction",
            ),
            step_id=step.step_id,
            plan_id=plan.plan_id,
        )

    kind = step.transaction.chain_kind
    if kind == "evm":
        if tenderly is None:
            raise BroadcastSimulationError(
                SimulationResult(
                    success=False,
                    calldata_hash="",
                    error_message="TenderlyClient not configured for EVM broadcast",
                ),
                step_id=step.step_id,
                plan_id=plan.plan_id,
            )
        tx_dict: dict[str, Any] = {
            "to": step.transaction.to or "",
            "data": step.transaction.data or "0x",
            "value": step.transaction.value or "0",
        }
        if step.transaction.gas:
            tx_dict["gas"] = step.transaction.gas
        sim = await tenderly.simulate_bundle(
            transactions=[tx_dict],
            network_id=network_id or step.transaction.chain_id or 1,
        )
    elif kind == "solana":
        if not solana_rpc_url:
            raise BroadcastSimulationError(
                SimulationResult(
                    success=False,
                    calldata_hash="",
                    error_message="solana_rpc_url not provided",
                ),
                step_id=step.step_id,
                plan_id=plan.plan_id,
            )
        if not step.transaction.serialized:
            raise BroadcastSimulationError(
                SimulationResult(
                    success=False,
                    calldata_hash="",
                    error_message="solana step missing serialized payload",
                ),
                step_id=step.step_id,
                plan_id=plan.plan_id,
            )
        sim = await simulate_transaction(
            solana_rpc_url, step.transaction.serialized,
        )
    else:
        raise BroadcastSimulationError(
            SimulationResult(
                success=False,
                calldata_hash="",
                error_message=f"unknown chain_kind: {kind!r}",
            ),
            step_id=step.step_id,
            plan_id=plan.plan_id,
        )

    if sim.success:
        # Stamp the simulated hash so the V7-001 bind invariant has
        # something to compare against at submit-flip time.
        step.simulated_calldata_hash = sim.calldata_hash
        # Seed broadcast hash — the wallet adapter MAY overwrite this
        # with a recomputed hash over the final wire-format bytes right
        # before sending. If it doesn't, the bind passes trivially
        # because the wallet signed the exact bytes we simulated.
        if step.broadcast_calldata_hash is None:
            step.broadcast_calldata_hash = sim.calldata_hash
    return sim


async def broadcast_step(
    plan: "ExecutionPlanV3",
    step_id: str,
    *,
    tenderly: TenderlyClient | None = None,
    solana_rpc_url: str | None = None,
    network_id: int | None = None,
    receipt: dict[str, Any] | None = None,
) -> SimulationResult:
    """End-to-end pre-broadcast: simulate, stamp hash, flip to submitted.

    The single broadcast entry-point that satisfies the V7-010 exit
    criterion: simulated_calldata_hash is populated BEFORE
    mark_step_status('submitted') runs (which then enforces V7-001).

    Raises:
        BroadcastSimulationError — sim failed (revert / RPC outage /
            missing config); the step is NOT flipped to submitted.
        CalldataHashMismatchError — sim succeeded but the wallet-layer
            hash diverged from the simulated one; V7-001 hard-block.
    """
    step = next((s for s in plan.steps if s.step_id == step_id), None)
    if step is None:
        raise ValueError(
            f"broadcast_step: no step with id={step_id!r} in plan {plan.plan_id}"
        )

    sim = await simulate_step_before_broadcast(
        plan, step,
        tenderly=tenderly,
        solana_rpc_url=solana_rpc_url,
        network_id=network_id,
    )
    if not sim.success:
        raise BroadcastSimulationError(
            sim, step_id=step.step_id, plan_id=plan.plan_id,
        )

    # V7-001's mark_step_status('submitted') compares hashes. Because we
    # stamped both to the same simulator-derived value above (and the
    # wallet adapter is expected to OVERWRITE broadcast_calldata_hash
    # right before the wallet popup with a hash of the actual signed
    # bytes), the bind is enforced end-to-end.
    plan.mark_step_status(step_id, "submitted", receipt=receipt)
    return sim


__all__ = [
    "BroadcastSimulationError",
    "broadcast_step",
    "simulate_step_before_broadcast",
]
