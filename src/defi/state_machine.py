"""Spec §5 — canonical state machine for the prompt-to-tx lifecycle.

The mermaid diagram in spec §5 is the authoritative graph: every
implementation detail must be expressible as a transition in this
graph. This module ships the enum + transition table; the runtime
consumes them to enforce that no plan flips between states the spec
doesn't admit.

States:
  PROMPTED → PARSING → (CLARIFYING ↔ PARSING)
  PARSING → RESOLVING → (CLARIFYING ↔ RESOLVING)
  RESOLVING → SIZING → PREVIEWING → SHIELDING → (BLOCKED | SIMULATING)
  SIMULATING → READY_TO_SIGN → (RE_SIMULATING if >30s elapsed)
  RE_SIMULATING → READY_TO_SIGN
  READY_TO_SIGN → SIGNING → (CANCELLED | BROADCASTED)
  BROADCASTED → CONFIRMING → (FAILED | VERIFYING)
  VERIFYING → INDEXED
  CONFIRMING → STUCK_RECOVERY (timeout / underpriced gas)
  STUCK_RECOVERY → (BROADCASTED via RBF | CANCELLED)
  FAILED → STUCK_BALANCE_FLOW (intermediate leg succeeded but tx N+1
    failed) → (RESOLVING via auto-rebuild | REFUNDING via user pick)
  INDEXED is the terminal happy state.
  BROADCASTED → PENDING_DST_FILL for cross-chain bridge legs.
  PENDING_DST_FILL → REBUILDING → PREVIEWING (re-enters pipeline with
    actual fill amount).
"""
from __future__ import annotations

from enum import Enum


class PipelineState(str, Enum):
    PROMPTED = "Prompted"
    PARSING = "Parsing"
    CLARIFYING = "Clarifying"
    RESOLVING = "Resolving"
    SIZING = "Sizing"
    PREVIEWING = "Previewing"
    SHIELDING = "Shielding"
    BLOCKED = "Blocked"
    SIMULATING = "Simulating"
    READY_TO_SIGN = "ReadyToSign"
    RE_SIMULATING = "ReSimulating"
    SIGNING = "Signing"
    BROADCASTED = "Broadcasted"
    CONFIRMING = "Confirming"
    VERIFYING = "Verifying"
    INDEXED = "Indexed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    STUCK_RECOVERY = "StuckRecovery"
    STUCK_BALANCE_FLOW = "StuckBalanceFlow"
    REFUNDING = "Refunding"
    PENDING_DST_FILL = "PendingDstFill"
    REBUILDING = "Rebuilding"


# Adjacency list — each state lists every state reachable in one step.
# Transition NOT in this map = spec-illegal; runtime should refuse.
_TRANSITIONS: dict[PipelineState, frozenset[PipelineState]] = {
    PipelineState.PROMPTED: frozenset({PipelineState.PARSING}),
    PipelineState.PARSING: frozenset({
        PipelineState.CLARIFYING,
        PipelineState.RESOLVING,
    }),
    PipelineState.CLARIFYING: frozenset({
        PipelineState.PARSING,
        PipelineState.RESOLVING,
    }),
    PipelineState.RESOLVING: frozenset({
        PipelineState.CLARIFYING,
        PipelineState.SIZING,
    }),
    PipelineState.SIZING: frozenset({PipelineState.PREVIEWING}),
    PipelineState.PREVIEWING: frozenset({
        PipelineState.SIZING,           # user edits range / amount
        PipelineState.SHIELDING,
    }),
    PipelineState.SHIELDING: frozenset({
        PipelineState.BLOCKED,
        PipelineState.SIMULATING,
    }),
    PipelineState.BLOCKED: frozenset({
        PipelineState.RESOLVING,        # user picks alternative
        PipelineState.CANCELLED,
    }),
    PipelineState.SIMULATING: frozenset({
        PipelineState.PREVIEWING,       # simulation revert → show reason
        PipelineState.READY_TO_SIGN,
    }),
    PipelineState.READY_TO_SIGN: frozenset({
        PipelineState.RE_SIMULATING,    # >30s elapsed
        PipelineState.SIGNING,
    }),
    PipelineState.RE_SIMULATING: frozenset({PipelineState.READY_TO_SIGN}),
    PipelineState.SIGNING: frozenset({
        PipelineState.CANCELLED,
        PipelineState.BROADCASTED,
    }),
    PipelineState.BROADCASTED: frozenset({
        PipelineState.CONFIRMING,
        PipelineState.PENDING_DST_FILL,
    }),
    PipelineState.PENDING_DST_FILL: frozenset({PipelineState.REBUILDING}),
    PipelineState.REBUILDING: frozenset({PipelineState.PREVIEWING}),
    PipelineState.CONFIRMING: frozenset({
        PipelineState.VERIFYING,
        PipelineState.FAILED,
        PipelineState.STUCK_RECOVERY,
    }),
    PipelineState.STUCK_RECOVERY: frozenset({
        PipelineState.BROADCASTED,
        PipelineState.CANCELLED,
    }),
    PipelineState.VERIFYING: frozenset({PipelineState.INDEXED}),
    PipelineState.FAILED: frozenset({PipelineState.STUCK_BALANCE_FLOW}),
    PipelineState.STUCK_BALANCE_FLOW: frozenset({
        PipelineState.RESOLVING,
        PipelineState.REFUNDING,
    }),
    PipelineState.INDEXED: frozenset(),
    PipelineState.CANCELLED: frozenset(),
    PipelineState.REFUNDING: frozenset({PipelineState.CANCELLED}),
}


def is_legal_transition(from_state: PipelineState, to_state: PipelineState) -> bool:
    """Return True when (from → to) is admitted by spec §5."""
    return to_state in _TRANSITIONS.get(from_state, frozenset())


def reachable_from(state: PipelineState) -> frozenset[PipelineState]:
    """Direct successors. Use for UI showing 'next possible actions'."""
    return _TRANSITIONS.get(state, frozenset())


def terminal_states() -> frozenset[PipelineState]:
    """States that have no outgoing transitions — INDEXED and CANCELLED."""
    return frozenset(s for s, succ in _TRANSITIONS.items() if not succ)


def assert_transition(from_state: PipelineState, to_state: PipelineState) -> None:
    """Raise ValueError when (from → to) is not in the spec §5 graph."""
    if not is_legal_transition(from_state, to_state):
        raise ValueError(
            f"Illegal state transition {from_state.value} → {to_state.value} "
            f"(spec §5). Allowed from {from_state.value}: "
            f"{sorted(s.value for s in reachable_from(from_state))}."
        )
