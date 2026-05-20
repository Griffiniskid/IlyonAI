"""Pin tests for BUG-F-05 / BUG-F-P1-F-06 (matrix Pass A wave 2) —
err_envelope code normalizer.

The plan-side ExecutionPlanV3.add_blocker normalizer (BUG-F-01..05 fix)
only catches blocker codes that flow through a card. simulate_swap and
build_swap_tx return their errors via err_envelope (no card constructed),
so their lowercase codes (quote_unavailable, etc.) bypass the plan-side
normalizer and surface to the user as-is.

This sibling normalizer at err_envelope's construction site mirrors the
same alias table, so the agent loop's tool-result handler sees canonical
UPPER_SNAKE codes that pass KNOWN_BLOCKER_CODES validation and
case-sensitive recovery dispatch.
"""
from __future__ import annotations

import pytest

from src.agent.tools._base import err_envelope, _normalize_err_code


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("quote_unavailable", "NULL_ROUTE"),
        ("pool_not_found", "UNSUPPORTED_ADAPTER"),
        ("unsupported_chain", "WALLET_CHAIN_MISMATCH"),
        ("missing_allowance", "APPROVAL_MISSING"),
        ("insufficient_balance", "INSUFFICIENT_BALANCE"),
        ("gas_top_up", "GAS_TOPUP_REQUIRED"),
        ("gas_topup", "GAS_TOPUP_REQUIRED"),
        ("adapter_build_failed", "ADAPTER_BUILD_FAILED"),
        ("adapter_quote_required", "ADAPTER_QUOTE_REQUIRED"),
        ("stale_price", "STALE_PRICE_FEED"),
        ("pool_not_initialized", "POOL_NOT_INITIALIZED"),
        ("zero_quote", "NULL_ROUTE"),
        ("composed_plan_bridge_quote_failed", "ADAPTER_QUOTE_REQUIRED"),
        ("composed_plan_bridge_build_failed", "ADAPTER_BUILD_FAILED"),
    ],
)
def test_lowercase_alias_maps_to_canonical(raw, canonical):
    assert _normalize_err_code(raw) == canonical


def test_canonical_passes_through_unchanged():
    assert _normalize_err_code("NULL_ROUTE") == "NULL_ROUTE"
    assert _normalize_err_code("INSUFFICIENT_BALANCE") == "INSUFFICIENT_BALANCE"


def test_unknown_code_preserved():
    assert _normalize_err_code("some_brand_new_code") == "some_brand_new_code"


def test_empty_code_handled():
    assert _normalize_err_code(None) is None
    assert _normalize_err_code("") == ""


def test_err_envelope_normalizes_at_construction():
    env = err_envelope("quote_unavailable", "no quote")
    assert env.error.code == "NULL_ROUTE"
    assert env.error.message == "no quote"


def test_err_envelope_preserves_canonical_code():
    env = err_envelope("INSUFFICIENT_BALANCE", "not enough USDC")
    assert env.error.code == "INSUFFICIENT_BALANCE"
