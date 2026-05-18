"""V7-068 — Global "never auto-refund-swap-back" guard pin tests.

Spec §6f hard rule: the assistant must never auto-swap a refunded
output back to the input asset without explicit user consent. This
test pins the shield-side chokepoint that enforces the rule, plus the
recovery-dispatcher wire that consumes it.
"""
from __future__ import annotations

import pytest

from src.shield.refund_guard import (
    FORBIDDEN_REFUND_CODES,
    FORBIDDEN_REFUND_SWAP_BACK_BLOCKER_CODE,
    guard_refund,
)


# ---------------------------------------------------------------------------
# Forbidden-action recognition
# ---------------------------------------------------------------------------


def test_refund_swap_compound_label_is_forbidden():
    """V7-068 — free-form 'swap_refund_back' must trip the substring rule."""
    assert guard_refund("swap_refund_back", {}) == "FORBIDDEN_REFUND_SWAP_BACK"


def test_normal_swap_label_is_allowed():
    """V7-068 — vanilla `normal_swap` is not a refund-swap-back action."""
    assert guard_refund("normal_swap", {}) is None


def test_empty_string_action_is_noop():
    """V7-068 — empty action label means nothing to guard against."""
    assert guard_refund("", {}) is None


def test_none_action_is_noop():
    """V7-068 — None action label means nothing to guard against."""
    # `action` typed as str but tolerate None via the falsy short-circuit.
    assert guard_refund(None, {}) is None  # type: ignore[arg-type]


def test_exact_refund_swap_back_token_is_forbidden():
    """V7-068 — verbatim FORBIDDEN_REFUND_CODES membership is blocked."""
    for code in FORBIDDEN_REFUND_CODES:
        assert guard_refund(code, {}) == "FORBIDDEN_REFUND_SWAP_BACK"


def test_auto_swap_refund_label_is_forbidden():
    """V7-068 — 'auto_swap_refund' substring co-occurrence is forbidden."""
    assert guard_refund("auto_swap_refund", {"chain": "ethereum"}) == \
        "FORBIDDEN_REFUND_SWAP_BACK"


def test_camel_case_refund_swap_back_is_forbidden():
    """V7-068 — `refundSwapBack` must be caught (case-insensitive)."""
    assert guard_refund("refundSwapBack", {}) == "FORBIDDEN_REFUND_SWAP_BACK"


def test_deposit_action_is_allowed():
    """V7-068 — 'deposit' is not a refund-swap action."""
    assert guard_refund("deposit", {}) is None


def test_withdraw_action_is_allowed():
    """V7-068 — 'withdraw' is not a refund-swap action."""
    assert guard_refund("withdraw", {}) is None


def test_blocker_constant_is_canonical_token():
    """V7-068 — the constant matches the spec §6c token verbatim."""
    assert FORBIDDEN_REFUND_SWAP_BACK_BLOCKER_CODE == "FORBIDDEN_REFUND_SWAP_BACK"


# ---------------------------------------------------------------------------
# Recovery-dispatcher wire (V7-068 integration)
# ---------------------------------------------------------------------------


def test_decide_recovery_refuses_proposed_refund_swap_back():
    """V7-068 — decide_recovery short-circuits on a forbidden proposed_action."""
    from src.defi.recovery import RecoveryAction, decide_recovery, FailureKind

    rec = decide_recovery(
        FailureKind.SLIPPAGE_BREACH,
        step_kind="deposit",
        elapsed_since_fail_s=10,
        proposed_action="REFUND_SWAP_BACK",
    )
    assert rec.action == RecoveryAction.NO_AUTO
    assert "Refused" in rec.posture
    assert "FORBIDDEN_REFUND_SWAP_BACK" in rec.rationale


def test_decide_recovery_does_not_refuse_normal_action():
    """V7-068 — proposed_action=None must not affect normal decision tree."""
    from src.defi.recovery import RecoveryAction, decide_recovery, FailureKind

    rec = decide_recovery(
        FailureKind.SLIPPAGE_BREACH,
        step_kind="deposit",
        elapsed_since_fail_s=10,
        current_slippage_bps=50,
        user_slippage_cap_bps=500,
    )
    # Slippage breach within 5 min → AUTO_REBUILD, not NO_AUTO.
    assert rec.action == RecoveryAction.AUTO_REBUILD
