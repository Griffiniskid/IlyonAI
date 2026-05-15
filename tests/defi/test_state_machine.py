"""Tests for spec §5 canonical state machine."""
from __future__ import annotations

import pytest

from src.defi.state_machine import (
    PipelineState,
    assert_transition,
    is_legal_transition,
    reachable_from,
    terminal_states,
)


def test_legal_prompted_to_parsing():
    assert is_legal_transition(PipelineState.PROMPTED, PipelineState.PARSING)


def test_legal_parsing_can_clarify():
    assert is_legal_transition(PipelineState.PARSING, PipelineState.CLARIFYING)


def test_legal_clarifying_back_to_parsing():
    assert is_legal_transition(PipelineState.CLARIFYING, PipelineState.PARSING)


def test_legal_ready_to_sign_30s_resim_then_back():
    assert is_legal_transition(PipelineState.READY_TO_SIGN, PipelineState.RE_SIMULATING)
    assert is_legal_transition(PipelineState.RE_SIMULATING, PipelineState.READY_TO_SIGN)


def test_legal_broadcasted_pending_dst_fill():
    # Cross-chain bridge leg path.
    assert is_legal_transition(PipelineState.BROADCASTED, PipelineState.PENDING_DST_FILL)
    assert is_legal_transition(PipelineState.PENDING_DST_FILL, PipelineState.REBUILDING)
    assert is_legal_transition(PipelineState.REBUILDING, PipelineState.PREVIEWING)


def test_legal_failed_to_stuck_balance_flow():
    assert is_legal_transition(PipelineState.FAILED, PipelineState.STUCK_BALANCE_FLOW)


def test_legal_stuck_balance_to_resolving_or_refunding():
    succ = reachable_from(PipelineState.STUCK_BALANCE_FLOW)
    assert PipelineState.RESOLVING in succ
    assert PipelineState.REFUNDING in succ


def test_illegal_prompted_to_indexed():
    assert not is_legal_transition(PipelineState.PROMPTED, PipelineState.INDEXED)


def test_illegal_ready_to_sign_skip_signing_to_indexed():
    # Spec §5: must go through SIGNING → BROADCASTED → CONFIRMING → VERIFYING → INDEXED.
    assert not is_legal_transition(PipelineState.READY_TO_SIGN, PipelineState.INDEXED)


def test_terminal_states_are_indexed_and_cancelled():
    terms = terminal_states()
    assert PipelineState.INDEXED in terms
    assert PipelineState.CANCELLED in terms
    # FAILED is NOT terminal — it routes to STUCK_BALANCE_FLOW first.
    assert PipelineState.FAILED not in terms


def test_assert_transition_raises_on_illegal():
    with pytest.raises(ValueError, match="Illegal state transition"):
        assert_transition(PipelineState.PROMPTED, PipelineState.INDEXED)


def test_assert_transition_silent_on_legal():
    # No raise.
    assert_transition(PipelineState.PROMPTED, PipelineState.PARSING)
    assert_transition(PipelineState.VERIFYING, PipelineState.INDEXED)


def test_every_non_terminal_has_at_least_one_successor():
    for state in PipelineState:
        succ = reachable_from(state)
        # Terminal states (INDEXED, CANCELLED) have empty succ.
        if state in {PipelineState.INDEXED, PipelineState.CANCELLED}:
            assert succ == frozenset()
        else:
            assert succ, f"state {state.value} has no successor"


def test_refunding_terminal_via_cancelled():
    # REFUNDING → CANCELLED (terminal), no other transitions.
    assert reachable_from(PipelineState.REFUNDING) == frozenset({PipelineState.CANCELLED})


def test_legal_signing_can_cancel_or_broadcast():
    succ = reachable_from(PipelineState.SIGNING)
    assert succ == frozenset({PipelineState.CANCELLED, PipelineState.BROADCASTED})


def test_legal_confirming_three_outcomes():
    succ = reachable_from(PipelineState.CONFIRMING)
    assert PipelineState.VERIFYING in succ
    assert PipelineState.FAILED in succ
    assert PipelineState.STUCK_RECOVERY in succ
