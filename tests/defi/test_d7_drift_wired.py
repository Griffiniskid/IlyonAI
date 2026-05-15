"""§11 D.7 — drift gate wired into plan.mark_step_status broadcast flip."""
from __future__ import annotations

import os

import pytest

from src.defi.execution.models import (
    ExecutionPlanV3,
    ExecutionStepV3,
    UnsignedStepTransaction,
    make_step,
)


def _plan_with_step(sim_quote=None, cur_quote=None, simulated_at=None):
    plan = ExecutionPlanV3.new(title="t", summary="s")
    step = make_step(
        index=1, action="supply", title="t", description="d",
        chain="ethereum", wallet="MetaMask", protocol="aave-v3",
        asset_in="USDC", amount_in="100",
        slippage_bps=50, gas_estimate_usd=2.0, duration_estimate_s=20,
        transaction=UnsignedStepTransaction(
            chain_kind="evm", chain_id=1,
            to="0xa", data="0x", value="0x0", spender="0xa",
        ),
        status="ready",
    )
    plan.steps = [step]
    plan.status = "ready"  # state machine: ready → executing legal
    plan.metadata = {}
    if sim_quote is not None:
        plan.metadata["simulated_quote"] = sim_quote
    if cur_quote is not None:
        plan.metadata["current_quote"] = cur_quote
    if simulated_at is not None:
        plan.simulated_at = simulated_at
    return plan, step


def test_no_quote_metadata_passes_through():
    """When neither simulated nor current quote present, D.7 noops."""
    plan, step = _plan_with_step()
    plan.mark_step_status(step.step_id, "submitted")
    assert step.status == "submitted"


def test_within_threshold_passes():
    plan, step = _plan_with_step(sim_quote=1000.0, cur_quote=1001.0)
    plan.mark_step_status(step.step_id, "submitted")
    # 10 bps drift, under 50 bps default
    assert step.status == "submitted"


def test_breach_refuses_flip():
    plan, step = _plan_with_step(sim_quote=1000.0, cur_quote=1100.0)
    plan.mark_step_status(step.step_id, "submitted")
    # 1000 bps drift — far over 50 — flip refused (status stays ready)
    assert step.status == "ready"


def test_strict_mode_raises_on_breach(monkeypatch):
    monkeypatch.setenv("IL_STRICT_STATE", "1")
    plan, step = _plan_with_step(sim_quote=1000.0, cur_quote=1100.0)
    with pytest.raises(ValueError, match="Price drift"):
        plan.mark_step_status(step.step_id, "submitted")
    monkeypatch.delenv("IL_STRICT_STATE")


def test_only_sim_quote_set_passes_through():
    """Single-quote present means we can't compare; D.7 noops."""
    plan, step = _plan_with_step(sim_quote=1000.0)
    plan.mark_step_status(step.step_id, "submitted")
    assert step.status == "submitted"


def test_other_status_changes_skip_d7_gate():
    """D.7 only fires on 'submitted'. Flipping to 'confirmed' must pass."""
    plan, step = _plan_with_step(sim_quote=1000.0, cur_quote=1100.0)
    # 1000 bps drift but the user is flipping to 'confirmed' (post-broadcast)
    plan.mark_step_status(step.step_id, "confirmed")
    assert step.status == "confirmed"
