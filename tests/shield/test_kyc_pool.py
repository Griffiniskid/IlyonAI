"""Pin tests for V7-033 / spec §13 row 10 — PERMISSIONED_POOL_KYC.

Covers the registry lookup primitives and the preflight wire that
emits one ExecutionBlocker per gated pool address. The registry
must be case-insensitive (EIP-55 mixed-case inputs); the preflight
wire must dedupe per-address so two steps referencing the same
gated pool surface a single blocker; unknown pools must never
synthesise a false-positive blocker.
"""
from __future__ import annotations

import pytest

from src.shield.kyc_pool import (
    KYC_GATED_POOLS,
    PERMISSIONED_POOL_KYC_BLOCKER_CODE,
    check_kyc_pool,
    evaluate_kyc_pool_preflight,
    is_kyc_gated,
)

# Pull a canonical registered address out of the static registry rather
# than hard-coding one — keeps the test honest against future churn.
REGISTERED_ADDR = next(iter(KYC_GATED_POOLS))
RANDOM_ADDR = "0xDeadBeef00000000000000000000000000000000"


def test_is_kyc_gated_returns_true_for_registered_addr_case_insensitive() -> None:
    # exact lowercase match
    assert is_kyc_gated(REGISTERED_ADDR) is True
    # EIP-55 mixed-case must still match
    assert is_kyc_gated(REGISTERED_ADDR.upper()) is True
    mixed = "0x" + REGISTERED_ADDR[2:4].upper() + REGISTERED_ADDR[4:]
    assert is_kyc_gated(mixed) is True


def test_is_kyc_gated_returns_false_for_random_addr() -> None:
    assert is_kyc_gated(RANDOM_ADDR) is False
    assert is_kyc_gated("") is False
    assert is_kyc_gated(None) is False  # type: ignore[arg-type]


def test_check_kyc_pool_returns_code_for_gated_else_none() -> None:
    assert check_kyc_pool(REGISTERED_ADDR) == PERMISSIONED_POOL_KYC_BLOCKER_CODE
    assert check_kyc_pool(REGISTERED_ADDR.upper()) == PERMISSIONED_POOL_KYC_BLOCKER_CODE
    assert check_kyc_pool(RANDOM_ADDR) is None
    assert check_kyc_pool("") is None


def test_evaluate_kyc_pool_preflight_returns_blockers_list() -> None:
    # empty input → empty output, never raises
    assert evaluate_kyc_pool_preflight([]) == []
    assert evaluate_kyc_pool_preflight([RANDOM_ADDR]) == []

    blockers = evaluate_kyc_pool_preflight([REGISTERED_ADDR])
    assert len(blockers) == 1
    b = blockers[0]
    assert b.code == PERMISSIONED_POOL_KYC_BLOCKER_CODE
    assert b.severity == "blocker"
    assert b.recoverable is False
    assert REGISTERED_ADDR in b.detail


def test_evaluate_kyc_pool_preflight_dedupes_case_insensitively() -> None:
    # same gated addr referenced twice (one mixed-case) → single blocker
    blockers = evaluate_kyc_pool_preflight(
        [REGISTERED_ADDR, REGISTERED_ADDR.upper(), RANDOM_ADDR]
    )
    assert len(blockers) == 1
    assert blockers[0].code == PERMISSIONED_POOL_KYC_BLOCKER_CODE


def test_evaluate_kyc_pool_preflight_propagates_affected_step_ids() -> None:
    blockers = evaluate_kyc_pool_preflight(
        [REGISTERED_ADDR], affected_step_ids=["step_001", "step_002"]
    )
    assert len(blockers) == 1
    assert blockers[0].affected_step_ids == ["step_001", "step_002"]
