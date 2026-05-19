"""Pin tests for BUG-F-01..05 (matrix Pass A) — blocker code normalization.

Three upstream emitters hand-mint lowercase blocker codes upstream of
`scan_scenario_blockers`, so they bypass KNOWN_BLOCKER_CODES validation
and the recovery enrichment pipeline. The chokepoint normalizer at
`ExecutionPlanV3.add_blocker` maps them to canonical UPPER_SNAKE form.

This pin test locks the alias table and exercises the normalizer
end-to-end via `add_blocker`.
"""
from __future__ import annotations

import pytest

from src.defi.execution.models import (
    KNOWN_BLOCKER_CODES,
    ExecutionBlocker,
    ExecutionPlanV3,
)


def _plan() -> ExecutionPlanV3:
    return ExecutionPlanV3.new(title="t", summary="s")


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("pool_not_found", "UNSUPPORTED_ADAPTER"),
        ("unsupported_chain", "WALLET_CHAIN_MISMATCH"),
        ("quote_unavailable", "NULL_ROUTE"),
        ("missing_allowance", "APPROVAL_MISSING"),
        ("insufficient_balance", "INSUFFICIENT_BALANCE"),
        ("gas_top_up", "GAS_TOPUP_REQUIRED"),
        ("gas_topup", "GAS_TOPUP_REQUIRED"),
        ("adapter_build_failed", "ADAPTER_BUILD_FAILED"),
        ("adapter_quote_required", "ADAPTER_QUOTE_REQUIRED"),
        ("stale_price", "STALE_PRICE_FEED"),
        ("pool_not_initialized", "POOL_NOT_INITIALIZED"),
        ("dust_below_threshold", "DUST_BELOW_THRESHOLD"),
    ],
)
def test_lowercase_alias_maps_to_canonical(raw, canonical):
    plan = _plan()
    plan.add_blocker(ExecutionBlocker(
        code=raw, severity="blocker", title="x", detail="y",
    ))
    assert plan.blockers[0].code == canonical
    assert plan.blockers[0].code in KNOWN_BLOCKER_CODES


def test_canonical_code_passes_through_unchanged():
    plan = _plan()
    plan.add_blocker(ExecutionBlocker(
        code="DUST_BELOW_THRESHOLD", severity="warning", title="x", detail="y",
    ))
    assert plan.blockers[0].code == "DUST_BELOW_THRESHOLD"


def test_upper_snake_fallback_for_unknown_lowercase():
    """If an emitter passes 'INSUFFICIENT_BALANCE' as lowercase 'insufficient_balance',
    normalization should still find the canonical KNOWN_BLOCKER_CODES match."""
    plan = _plan()
    plan.add_blocker(ExecutionBlocker(
        code="self_trade_against_own_lp", severity="blocker", title="x", detail="y",
    ))
    # Not in the alias table, but uppercasing finds it in KNOWN_BLOCKER_CODES.
    assert plan.blockers[0].code == "SELF_TRADE_AGAINST_OWN_LP"


def test_genuinely_unknown_code_left_as_is():
    """Unknown code (no alias + UPPER_SNAKE not in KNOWN_BLOCKER_CODES) is
    preserved unchanged so the caller can debug."""
    plan = _plan()
    plan.add_blocker(ExecutionBlocker(
        code="some_brand_new_code", severity="blocker", title="x", detail="y",
    ))
    assert plan.blockers[0].code == "some_brand_new_code"


def test_blocker_fields_preserved_through_normalization():
    plan = _plan()
    plan.add_blocker(ExecutionBlocker(
        code="pool_not_found",
        severity="blocker",
        title="Pool not found",
        detail="The requested pool slug did not match any indexed pool.",
        affected_step_ids=["step_abc", "step_def"],
        recoverable=True,
        cta="Re-send with a recognized protocol + pair.",
    ))
    b = plan.blockers[0]
    assert b.code == "UNSUPPORTED_ADAPTER"
    assert b.severity == "blocker"
    assert b.title == "Pool not found"
    assert "did not match" in b.detail
    assert b.affected_step_ids == ["step_abc", "step_def"]
    assert b.recoverable is True
    assert "Re-send" in b.cta


def test_empty_or_whitespace_code_no_op():
    plan = _plan()
    plan.add_blocker(ExecutionBlocker(
        code="", severity="warning", title="x", detail="y",
    ))
    assert plan.blockers[0].code == ""


def test_status_flips_to_blocked_on_blocker_severity():
    plan = _plan()
    plan.add_blocker(ExecutionBlocker(
        code="pool_not_found", severity="blocker", title="x", detail="y",
    ))
    assert plan.status == "blocked"
