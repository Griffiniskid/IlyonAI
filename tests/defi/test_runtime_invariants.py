"""Pin tests for the runtime invariant assertion layer.

Wave 8 validation infra. Tests for src/agent/runtime_invariants.py:
  - I1: signable step has non-null transaction
  - I2: tx_count ↔ requires_signature consistency
  - I3: USD value overflow clamp ($1e10 threshold)
  - I4: step-index continuity (no silent gaps)
  - I6: executable:false ⇒ blocker required

Plus positive cases (clean cards pass through) and end-to-end via
StreamCollector.emit_card.
"""
from __future__ import annotations

from src.agent.runtime_invariants import (
    check_card_invariants,
    enforce_card_invariants,
)


# ─── I1: signable step has non-null transaction ──────────────────────────


def test_i1_ready_step_with_null_tx_violates():
    """BUG-E-003 / P0-H-08 shape — composed plan emits status:ready bridge
    step with transaction:null."""
    payload = {
        "status": "ready",
        "steps": [
            {
                "index": 0,
                "action": "bridge",
                "status": "ready",
                "blocker_codes": [],
                "transaction": None,
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I1" for v in violations)


def test_i1_ready_step_with_blocker_codes_allowed():
    """Step with explicit blocker_codes may have null transaction
    (deferred PENDING_DST_FILL semantics)."""
    payload = {
        "steps": [
            {
                "index": 0,
                "action": "deposit_lp",
                "status": "pending",
                "blocker_codes": ["PENDING_DST_FILL"],
                "transaction": None,
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I1" for v in violations)


def test_i1_signable_step_with_tx_passes():
    """Normal signable plan: step has status:ready + transaction:{...}."""
    payload = {
        "steps": [
            {
                "index": 1,
                "action": "supply",
                "status": "ready",
                "blocker_codes": [],
                "transaction": {"to": "0xabc", "data": "0xdead", "value": "0x0"},
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I1" for v in violations)


def test_i1_enforce_replaces_with_invariant_violation_card():
    """When I1 fires, enforce_card_invariants replaces the card with a
    structured invariant_violation blocker."""
    payload = {
        "steps": [
            {"index": 0, "status": "ready", "blocker_codes": [], "transaction": None},
        ],
    }
    new_type, new_payload, violations = enforce_card_invariants(
        "plan_abc", "execution_plan_v3", payload
    )
    assert new_type == "invariant_violation"
    assert new_payload["kind"] == "invariant_violation"
    assert any(v["id"] == "I1" for v in new_payload["violations"])


# ─── I2: tx_count ↔ requires_signature consistency ───────────────────────


def test_i2_tx_count_nonzero_but_requires_signature_false_violates():
    """D-P1-01/B-series shape — plan ships 4 steps with
    requires_signature:false."""
    payload = {
        "tx_count": 4,
        "requires_signature": False,
        "steps": [{"index": i, "status": "ready", "transaction": {"to": "0x"}} for i in range(1, 5)],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I2" for v in violations)


def test_i2_tx_count_zero_with_requires_signature_false_passes():
    payload = {"tx_count": 0, "requires_signature": False, "steps": []}
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I2" for v in violations)


def test_i2_signature_count_in_totals_block_also_checked():
    """Some payloads carry counts under `totals` instead of top-level."""
    payload = {
        "totals": {"signatures_required": 3},
        "requires_signature": False,
        "steps": [{"index": i, "status": "ready", "transaction": {"to": "0x"}} for i in range(1, 4)],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I2" for v in violations)


# ─── I3: USD value overflow clamp ────────────────────────────────────────


def test_i3_usd_value_overflow_violates():
    """NEW-P0-F-09 wallet spark token usd_value = 4.99e+30."""
    payload = {
        "balances": [
            {"chain": "Base", "token": "spark", "usd_value": 4.99e30},
        ],
        "total_usd": 4.99e30,
    }
    violations = check_card_invariants("balance_report", payload)
    assert sum(1 for v in violations if v.invariant_id == "I3") >= 2


def test_i3_normal_usd_values_pass():
    payload = {"total_usd": 1234.56, "usd_value": 999.99}
    violations = check_card_invariants("balance_report", payload)
    assert not any(v.invariant_id == "I3" for v in violations)


def test_i3_enforce_clamps_overflow_to_none():
    """I3 doesn't refuse the card — it sanitizes the bad fields."""
    payload = {
        "balances": [{"token": "spark", "usd_value": 5e30}],
        "total_usd": 5e30,
    }
    new_type, new_payload, _v = enforce_card_invariants(
        "bal_1", "balance_report", payload
    )
    # Card still emitted (not refused) but USD fields clamped.
    assert new_type == "balance_report"
    assert new_payload["total_usd"] is None
    assert new_payload["balances"][0]["usd_value"] is None


# ─── I4: step-index continuity ───────────────────────────────────────────


def test_i4_step_index_gap_violates():
    """NEW-P0-F-10 / N-B-W6-03 — alloc has 5 positions, plan ships
    [1,2,4,5] missing 3."""
    payload = {
        "steps": [
            {"index": 1, "status": "ready", "transaction": {"to": "0x"}},
            {"index": 2, "status": "ready", "transaction": {"to": "0x"}},
            {"index": 4, "status": "ready", "transaction": {"to": "0x"}},
            {"index": 5, "status": "ready", "transaction": {"to": "0x"}},
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I4" for v in violations)


def test_i4_consecutive_indices_pass():
    payload = {
        "steps": [
            {"index": i, "status": "ready", "transaction": {"to": "0x"}}
            for i in (1, 2, 3, 4)
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I4" for v in violations)


def test_i4_zero_based_consecutive_passes():
    """Some plans use 0-based indexing (Step 0, Step 1, Step 2)."""
    payload = {
        "steps": [
            {"index": i, "status": "ready", "transaction": {"to": "0x"}}
            for i in (0, 1, 2)
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I4" for v in violations)


# ─── I6: executable:false ⇒ blocker required ─────────────────────────────


def test_i6_executable_false_step_without_blocker_violates():
    """NEW-A-W7-01 / N-B-W4-01 — alloc card has saturn marked
    executable:false but step ships supply with blocker:null."""
    payload = {
        "positions": [
            {"symbol": "SUSDAT", "executable": False, "adapter_id": None},
        ],
        "steps": [
            {
                "index": 1,
                "target": "SUSDAT · saturn",
                "blocker_codes": [],
                "status": "ready",
                "transaction": {"to": "0x"},
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I6" for v in violations)


def test_i6_fallback_adapter_treated_as_executable_false():
    """N-C-W7-03 — adapter_id ends in '-fallback' should trigger same
    constraint."""
    payload = {
        "positions": [
            {"symbol": "USDCHF-USDC", "adapter_id": "solana-yield-builder-fallback"},
        ],
        "steps": [
            {
                "index": 1,
                "target": "USDCHF-USDC · gmtrade",
                "blocker_codes": [],
                "status": "ready",
                "transaction": {"to": "0x"},
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I6" for v in violations)


def test_i6_executable_false_with_proper_blocker_passes():
    payload = {
        "positions": [
            {"symbol": "SUSDAT", "executable": False, "adapter_id": None},
        ],
        "steps": [
            {
                "index": 1,
                "target": "SUSDAT · saturn",
                "blocker_codes": ["UNSUPPORTED_ADAPTER"],
                "status": "blocked",
                "transaction": None,
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I6" for v in violations)


# ─── End-to-end via StreamCollector.emit_card ────────────────────────────


def test_emit_card_replaces_invariant_violating_payload():
    """A broken card hitting StreamCollector.emit_card must be replaced
    with the invariant_violation blocker."""
    from src.agent.streaming import StreamCollector
    from src.api.schemas.agent import CardFrame

    sc = StreamCollector()
    broken_payload = {
        "status": "ready",
        "steps": [
            {"index": 0, "status": "ready", "blocker_codes": [], "transaction": None},
        ],
    }
    sc.emit_card("plan_broken_1", "execution_plan_v3", broken_payload)
    frames = list(sc.drain())
    card = next(f for f in frames if isinstance(f, CardFrame))
    assert card.card_type == "invariant_violation"
    assert card.payload["kind"] == "invariant_violation"


def test_emit_card_passes_clean_card_through():
    """A well-formed card must pass through unchanged."""
    from src.agent.streaming import StreamCollector
    from src.api.schemas.agent import CardFrame

    sc = StreamCollector()
    clean_payload = {
        "steps": [
            {
                "index": 1,
                "action": "supply",
                "status": "ready",
                "blocker_codes": [],
                "transaction": {"to": "0xabc", "data": "0xdead", "value": "0x0"},
            },
        ],
    }
    sc.emit_card("plan_clean_1", "execution_plan_v3", clean_payload)
    frames = list(sc.drain())
    card = next(f for f in frames if isinstance(f, CardFrame))
    assert card.card_type == "execution_plan_v3"
    assert card.payload == clean_payload


def test_emit_card_clamps_usd_overflow_in_place():
    from src.agent.streaming import StreamCollector
    from src.api.schemas.agent import CardFrame

    sc = StreamCollector()
    payload = {"total_usd": 5e30, "balances": [{"usd_value": 5e30}]}
    sc.emit_card("bal_1", "balance_report", payload)
    frames = list(sc.drain())
    card = next(f for f in frames if isinstance(f, CardFrame))
    # Card still emitted as balance_report (not refused) but USD clamped.
    assert card.card_type == "balance_report"
    assert card.payload["total_usd"] is None
