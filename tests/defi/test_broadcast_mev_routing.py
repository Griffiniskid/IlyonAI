"""V7-037 wire-in pin — broadcast_step routes through private relay above threshold.

Audit gap: src/shield/mev_router.py defines should_route_private +
private_rpc_for_chain, but no caller in src/ outside the module itself.
broadcast_step now consults the router POST-sim, PRE-flip-to-submitted, and
stamps an observable `mev_routing` dict into the step's receipt so the
audit trail can prove the routing decision.

This test pins:
  - high-value Ethereum swap routes via `mevblocker` private lane
  - low-value Ethereum swap stays on `public` mempool
  - high-slippage cheap swap still routes private (slippage threshold)
  - Solana high-value swap routes via `jito` with tip lamports
  - unsupported chain (e.g. base) stays public even above threshold
  - public-routed receipt still carries the audit field
"""
from __future__ import annotations

import pytest

from src.defi.execution.broadcast import (
    _resolve_mev_routing,
    broadcast_step,
)
from src.defi.execution.models import (
    ExecutionPlanV3,
    UnsignedStepTransaction,
    make_step,
)
from src.defi.simulator.tenderly_client import SimulationResult, TenderlyClient
from src.shield.mev_router import MEVBLOCKER_RPC


class _StubTenderly(TenderlyClient):
    """Skip HTTP, return a canned SimulationResult."""

    def __init__(self, *, result: SimulationResult) -> None:
        self._result = result

    async def simulate_bundle(self, transactions, network_id):  # type: ignore[override]
        return self._result


def _plan_with_step(
    *,
    chain: str = "ethereum",
    chain_kind: str = "evm",
    chain_id: int | None = 1,
    slippage_bps: int | None = 20,
    serialized: str | None = None,
) -> ExecutionPlanV3:
    plan = ExecutionPlanV3.new(title="V7-037", summary="mev wire pin")
    tx = UnsignedStepTransaction(
        chain_kind=chain_kind,  # type: ignore[arg-type]
        chain_id=chain_id,
        to="0xabc" if chain_kind == "evm" else None,
        data="0xdeadbeef" if chain_kind == "evm" else None,
        value="0" if chain_kind == "evm" else None,
        serialized=serialized,
    )
    step = make_step(
        index=0,
        action="swap",
        title="Swap",
        description="t",
        chain=chain,
        wallet="MetaMask" if chain_kind == "evm" else "Phantom",
        protocol="enso",
        slippage_bps=slippage_bps,
        transaction=tx,
    )
    plan.add_step(step)
    return plan


# ---------------------------------------------------------------------------
# _resolve_mev_routing — pure-function shape pins
# ---------------------------------------------------------------------------

def test_resolve_mev_routing_ethereum_high_value_returns_mevblocker():
    plan = _plan_with_step(chain="ethereum", slippage_bps=10)
    info = _resolve_mev_routing(plan.steps[0], notional_usd=10_000.0)
    assert info["routed_via"] == "mevblocker"
    assert info["rpc_url"] == MEVBLOCKER_RPC
    assert info["chain"] == "ethereum"
    assert info["notional_usd"] == 10_000.0


def test_resolve_mev_routing_ethereum_low_value_low_slippage_public():
    plan = _plan_with_step(chain="ethereum", slippage_bps=10)
    info = _resolve_mev_routing(plan.steps[0], notional_usd=50.0)
    assert info["routed_via"] == "public"
    assert "rpc_url" not in info


def test_resolve_mev_routing_ethereum_high_slippage_private_even_cheap():
    # slippage > 30 bps flips private regardless of notional
    plan = _plan_with_step(chain="ethereum", slippage_bps=100)
    info = _resolve_mev_routing(plan.steps[0], notional_usd=50.0)
    assert info["routed_via"] == "mevblocker"


def test_resolve_mev_routing_solana_high_value_returns_jito():
    plan = _plan_with_step(
        chain="solana", chain_kind="solana", chain_id=None,
        slippage_bps=10, serialized="aGVsbG8=",
    )
    info = _resolve_mev_routing(plan.steps[0], notional_usd=10_000.0)
    assert info["routed_via"] == "jito"
    assert info["jito_tip_lamports"] > 0


def test_resolve_mev_routing_unsupported_chain_falls_back_public():
    plan = _plan_with_step(chain="base", chain_id=8453, slippage_bps=100)
    info = _resolve_mev_routing(plan.steps[0], notional_usd=10_000.0)
    # NOT-YET-WIRED: base has no private-relay config in mev_router yet.
    assert info["routed_via"] == "public"


# ---------------------------------------------------------------------------
# broadcast_step — end-to-end pins (mocked sim, real flow)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcast_step_high_value_ethereum_stamps_mevblocker():
    plan = _plan_with_step(chain="ethereum", slippage_bps=20)
    step = plan.steps[0]
    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash="a" * 64, gas_used=50_000,
    ))

    await broadcast_step(
        plan, step.step_id,
        tenderly=tenderly,
        notional_usd=10_000.0,
    )

    assert step.status == "submitted"
    assert step.receipt is not None
    mev = step.receipt["mev_routing"]
    assert mev["routed_via"] == "mevblocker"
    assert mev["rpc_url"] == MEVBLOCKER_RPC
    assert mev["notional_usd"] == 10_000.0


@pytest.mark.asyncio
async def test_broadcast_step_low_value_ethereum_stamps_public():
    plan = _plan_with_step(chain="ethereum", slippage_bps=10)
    step = plan.steps[0]
    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash="b" * 64, gas_used=50_000,
    ))

    await broadcast_step(
        plan, step.step_id,
        tenderly=tenderly,
        notional_usd=50.0,
    )

    assert step.status == "submitted"
    assert step.receipt is not None
    mev = step.receipt["mev_routing"]
    assert mev["routed_via"] == "public"
    # Public path must NOT leak a private rpc_url into the receipt.
    assert "rpc_url" not in mev


@pytest.mark.asyncio
async def test_broadcast_step_preserves_caller_receipt_fields():
    """`receipt` passed by caller must merge with mev_routing, not be overwritten."""
    plan = _plan_with_step(chain="ethereum", slippage_bps=10)
    step = plan.steps[0]
    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash="c" * 64,
    ))

    caller_receipt = {"tx_hash": "0xdead", "submitted_at": 123.45}
    await broadcast_step(
        plan, step.step_id,
        tenderly=tenderly,
        notional_usd=10_000.0,
        receipt=caller_receipt,
    )

    assert step.receipt["tx_hash"] == "0xdead"
    assert step.receipt["submitted_at"] == 123.45
    assert step.receipt["mev_routing"]["routed_via"] == "mevblocker"
    # Caller's dict must not be mutated.
    assert "mev_routing" not in caller_receipt


@pytest.mark.asyncio
async def test_broadcast_step_missing_notional_defaults_to_zero_and_slippage_only():
    """No notional → slippage alone decides. 20 bps < 30 → public."""
    plan = _plan_with_step(chain="ethereum", slippage_bps=20)
    step = plan.steps[0]
    tenderly = _StubTenderly(result=SimulationResult(
        success=True, calldata_hash="d" * 64,
    ))

    await broadcast_step(plan, step.step_id, tenderly=tenderly)

    mev = step.receipt["mev_routing"]
    assert mev["routed_via"] == "public"
    assert mev["notional_usd"] == 0.0
