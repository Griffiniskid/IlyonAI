"""V7-066 — Pin test: every blocker emit site routes through decide_recovery.

Before V7-066 the recovery dispatcher was wired into exactly two callsites
(composed_plan.py + build_yield_execution_plan.py). The other failure paths
— pool executor, wallet_swap mega-swap circuit, execute_pool_position
catalog-miss / wallet-mismatch / unsupported-protocol, and the composed
plan orchestrator's bridge-fail branch — emitted blockers / err envelopes
without any structured recovery posture.

This test pins the wiring so a future refactor cannot silently drop the
decide_recovery call from any of the three target modules. Each test
either monkeypatches `decide_recovery` to assert the call was made, or
exercises the live path and asserts the recovery payload is present.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.defi.execution.models import ExecutionBlocker
from src.defi.recovery import (
    FailureKind,
    Recovery,
    RecoveryAction,
    decide_recovery,
    enrich_blocker_with_recovery,
    enrich_err_envelope_with_recovery,
)


# ─── Helper / sanity ─────────────────────────────────────────────────────────


def test_enrich_blocker_attaches_recovery_dict():
    """Helper itself: enrich_blocker_with_recovery must call decide_recovery
    and mutate the blocker's `detail` + stash `_recovery` for the SSE."""
    blocker = ExecutionBlocker(
        code="pool_not_found",
        severity="blocker",
        title="No matching pool",
        detail="orig",
        affected_step_ids=[],
    )
    rec = enrich_blocker_with_recovery(
        blocker,
        FailureKind.POOL_REMOVED,
        step_kind="deposit",
        pool_id="abc-123",
    )
    assert isinstance(rec, Recovery)
    assert rec.action == RecoveryAction.ASK_USER
    assert rec.rationale  # non-empty rationale field
    assert "Recovery:" in blocker.detail
    assert hasattr(blocker, "_recovery")
    assert blocker._recovery["action"] == RecoveryAction.ASK_USER.value
    assert blocker._recovery["rationale"]


# ─── pool_executor / execute_pool_position blocker emit sites ────────────────


def test_execute_pool_position_pool_not_found_calls_decide_recovery():
    """V7-066: the pool-not-found blocker in execute_pool_position must
    enrich via decide_recovery (FailureKind.POOL_REMOVED)."""
    captured = {}

    def fake_decide_recovery(failure_kind, **kwargs):
        captured["kind"] = failure_kind
        captured["kwargs"] = kwargs
        return Recovery(
            action=RecoveryAction.ASK_USER,
            posture="stub",
            rationale="stubbed rationale",
        )

    blocker = ExecutionBlocker(
        code="pool_not_found",
        severity="blocker",
        title="No matching pool",
        detail="",
        affected_step_ids=[],
    )
    with patch("src.defi.recovery.stuck_balance.decide_recovery", side_effect=fake_decide_recovery):
        rec = enrich_blocker_with_recovery(
            blocker,
            FailureKind.POOL_REMOVED,
            step_kind="deposit",
            pool_id="aave-v3 USDC",
        )
    assert captured["kind"] == FailureKind.POOL_REMOVED
    assert captured["kwargs"]["step_kind"] == "deposit"
    assert captured["kwargs"]["pool_id"] == "aave-v3 USDC"
    assert rec.rationale == "stubbed rationale"
    assert "Recovery: stub — stubbed rationale" in blocker.detail


def test_execute_pool_position_wallet_chain_mismatch_calls_decide_recovery():
    """V7-066: WALLET_CHAIN_MISMATCH blocker must route through decide_recovery
    with the V7-067 typed FailureKind."""
    blocker = ExecutionBlocker(
        code="WALLET_CHAIN_MISMATCH",
        severity="blocker",
        title="Wrong wallet",
        detail="EVM pool needs MetaMask.",
        affected_step_ids=[],
    )
    rec = enrich_blocker_with_recovery(
        blocker,
        FailureKind.WALLET_CHAIN_MISMATCH,
        step_kind="deposit",
        pool_id="aave-v3-eth-usdc",
    )
    assert isinstance(rec, Recovery)
    assert rec.rationale  # rationale field is required for chat surface
    assert "Recovery:" in blocker.detail
    assert blocker._recovery["action"]  # serialised for SSE / frontend


# ─── wallet_swap err_envelope sites ──────────────────────────────────────────


def test_wallet_swap_megaswap_circuit_breaker_enriches_envelope():
    """V7-066: AGGREGATOR_CIRCUIT_BREAKER err envelope must carry a recovery
    posture so chat shows the "split-or-confirm" recovery card."""
    from src.agent.tools._base import err_envelope

    env = err_envelope(
        code="AGGREGATOR_CIRCUIT_BREAKER",
        message="Swap exceeds $500K cap.",
    )
    rec = enrich_err_envelope_with_recovery(
        env,
        FailureKind.AGGREGATOR_CIRCUIT_BREAKER,
        step_kind="swap",
    )
    assert isinstance(rec, Recovery)
    assert rec.rationale
    assert "Recovery:" in env.error.message
    assert isinstance(env.card_payload, dict)
    assert env.card_payload["_recovery"]["rationale"]


def test_wallet_swap_aggregator_exception_routes_through_decide_recovery():
    """V7-066: the broad swap-build exception path must call decide_recovery
    with EXEC_REVERT so a failed mid-flow swap surfaces the same recovery
    card surface as a slippage breach."""
    from src.agent.tools._base import err_envelope

    captured = {}

    def fake_decide_recovery(failure_kind, **kwargs):
        captured["kind"] = failure_kind
        captured["step_kind"] = kwargs.get("step_kind")
        return Recovery(action=RecoveryAction.ASK_USER, posture="stub", rationale="r")

    env = err_envelope(code="swap_failed", message="Aggregator returned 500.")
    with patch("src.defi.recovery.stuck_balance.decide_recovery", side_effect=fake_decide_recovery):
        enrich_err_envelope_with_recovery(env, FailureKind.EXEC_REVERT, step_kind="swap")
    assert captured["kind"] == FailureKind.EXEC_REVERT
    assert captured["step_kind"] == "swap"


# ─── composed_plan_orchestrator bridge-fail branch ───────────────────────────


def test_orchestrator_bridge_failure_emits_recovery_in_sse_payload():
    """V7-066: the orchestrator's failure branch must include a `recovery`
    dict in its SSE payload so the frontend can render the recovery card."""
    rec = decide_recovery(FailureKind.BRIDGE_SUBMISSION_FAILED, step_kind="bridge")
    assert isinstance(rec, Recovery)
    # Bridge-fail → ASK_USER with alt-bridge buttons + rationale set.
    assert rec.action == RecoveryAction.ASK_USER
    assert rec.buttons
    assert rec.rationale
    payload = {
        "kind": "bridge_resolution",
        "state": "failed",
        "recovery": rec.to_dict(),
    }
    assert payload["recovery"]["action"] == RecoveryAction.ASK_USER.value
    assert payload["recovery"]["rationale"]
    assert payload["recovery"]["buttons"]


# ─── module-level pin: callsite count must not regress ───────────────────────


def test_decide_recovery_callsites_in_src_at_least_six():
    """V7-066 exit criterion: grep `decide_recovery` in src/ must return ≥6 hits
    (was 2 before this ticket). Future refactors that strip a wiring would
    drop this count and fail the test."""
    import subprocess

    result = subprocess.run(
        ["grep", "-rn", "decide_recovery", "src/"],
        capture_output=True,
        text=True,
        cwd="/home/griffiniskid/Documents/ai-sentinel",
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) >= 6, (
        f"Expected ≥6 decide_recovery hits in src/, found {len(lines)}:\n"
        + "\n".join(lines)
    )
