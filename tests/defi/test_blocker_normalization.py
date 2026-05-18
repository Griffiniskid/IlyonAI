"""V7-062..V7-067 — pin tests for the blocker-code normalization batch.

Spec batch:
    V7-062 — UPPER_SNAKE casing on every blocker emitter (no more
             lowercase `unsupported_adapter` / `adapter_build_failed` /
             `wallet_chain_mismatch` / `aggregator_circuit`).
    V7-063 — GAS_TOP_UP renamed to GAS_TOPUP_REQUIRED canonical token.
    V7-064 — AGGREGATOR_CIRCUIT renamed to AGGREGATOR_CIRCUIT_BREAKER.
    V7-065 — NULL_ROUTE added to KNOWN_BLOCKER_CODES (was emitted by
             swap_simulate F09 path but never registered).
    V7-067 — FailureKind enum gained NULL_ROUTE / WALLET_CHAIN_MISMATCH /
             INSUFFICIENT_BALANCE / GAS_TOPUP_REQUIRED /
             AGGREGATOR_CIRCUIT_BREAKER values so the recovery
             dispatcher can route on a typed union.

These tests are intentionally redundant with the spec docs — they
exist to fail loudly the next time someone tries to revert one of the
codes back to the historical lowercase / under_scored form.
"""
from __future__ import annotations

from src.defi.execution.models import KNOWN_BLOCKER_CODES
from src.defi.recovery import FailureKind


# ---------------------------------------------------------------------------
# V7-062 — UPPER_SNAKE registration
# ---------------------------------------------------------------------------


def test_unsupported_adapter_in_known_blocker_codes():
    """V7-062 — `UNSUPPORTED_ADAPTER` must be the registered token."""
    assert "UNSUPPORTED_ADAPTER" in KNOWN_BLOCKER_CODES


def test_adapter_build_failed_in_known_blocker_codes():
    """V7-062 — `ADAPTER_BUILD_FAILED` must be the registered token."""
    assert "ADAPTER_BUILD_FAILED" in KNOWN_BLOCKER_CODES


def test_wallet_chain_mismatch_in_known_blocker_codes():
    """V7-062 — `WALLET_CHAIN_MISMATCH` must be the registered token."""
    assert "WALLET_CHAIN_MISMATCH" in KNOWN_BLOCKER_CODES


def test_insufficient_balance_in_known_blocker_codes():
    """V7-062 — `INSUFFICIENT_BALANCE` must be the registered token."""
    assert "INSUFFICIENT_BALANCE" in KNOWN_BLOCKER_CODES


# ---------------------------------------------------------------------------
# V7-063 — GAS_TOP_UP → GAS_TOPUP_REQUIRED rename
# ---------------------------------------------------------------------------


def test_gas_topup_required_in_known_blocker_codes():
    """V7-063 — canonical token is GAS_TOPUP_REQUIRED, not GAS_TOP_UP."""
    assert "GAS_TOPUP_REQUIRED" in KNOWN_BLOCKER_CODES


def test_gas_top_up_legacy_token_not_present():
    """V7-063 — legacy `GAS_TOP_UP` must not be present."""
    assert "GAS_TOP_UP" not in KNOWN_BLOCKER_CODES


# ---------------------------------------------------------------------------
# V7-064 — AGGREGATOR_CIRCUIT → AGGREGATOR_CIRCUIT_BREAKER rename
# ---------------------------------------------------------------------------


def test_aggregator_circuit_breaker_in_known_blocker_codes():
    """V7-064 — canonical token is AGGREGATOR_CIRCUIT_BREAKER."""
    assert "AGGREGATOR_CIRCUIT_BREAKER" in KNOWN_BLOCKER_CODES


# ---------------------------------------------------------------------------
# V7-065 — NULL_ROUTE registration
# ---------------------------------------------------------------------------


def test_null_route_in_known_blocker_codes():
    """V7-065 — F09 null-route blocker must be registered."""
    assert "NULL_ROUTE" in KNOWN_BLOCKER_CODES


# ---------------------------------------------------------------------------
# V7-067 — FailureKind enum coverage
# ---------------------------------------------------------------------------


def test_failure_kind_has_null_route():
    """V7-067 — FailureKind.NULL_ROUTE must exist."""
    assert FailureKind.NULL_ROUTE.value == "null_route"


def test_failure_kind_has_wallet_chain_mismatch():
    """V7-067 — FailureKind.WALLET_CHAIN_MISMATCH must exist."""
    assert FailureKind.WALLET_CHAIN_MISMATCH.value == "wallet_chain_mismatch"


def test_failure_kind_has_insufficient_balance():
    """V7-067 — FailureKind.INSUFFICIENT_BALANCE must exist."""
    assert FailureKind.INSUFFICIENT_BALANCE.value == "insufficient_balance"


def test_failure_kind_has_gas_topup_required():
    """V7-067 — FailureKind.GAS_TOPUP_REQUIRED must exist."""
    assert FailureKind.GAS_TOPUP_REQUIRED.value == "gas_topup_required"


def test_failure_kind_has_aggregator_circuit_breaker():
    """V7-067 — FailureKind.AGGREGATOR_CIRCUIT_BREAKER must exist."""
    assert FailureKind.AGGREGATOR_CIRCUIT_BREAKER.value == "aggregator_circuit_breaker"
