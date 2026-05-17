"""V7-001 pin test — simulated_calldata_hash == broadcast_calldata_hash.

Spec quote: "One Confirm button: produces an artifact hash; the wallet
popup's calldata must hash-match this artifact, or signing is refused.
Enforces simulated_calldata_hash == broadcast_calldata_hash"

Covers:
  - field round-trips through `ExecutionStepV3.to_dict`
  - `assert_calldata_match` raises on mismatch / missing hash
  - `compute_calldata_hash` is stable across dict-key ordering
  - `mark_step_status('submitted', ...)` with mismatched hashes raises
    `CalldataHashMismatchError`
"""
from __future__ import annotations

import pytest

from src.defi.execution.models import (
    ExecutionPlanV3,
    ExecutionStepV3,
    UnsignedStepTransaction,
    make_step,
)
from src.defi.execution.state_machine import (
    CalldataHashMismatchError,
    assert_calldata_match,
    compute_calldata_hash,
)


# ----------------------------------------------------------------------
# Field round-trip
# ----------------------------------------------------------------------
def test_field_roundtrips_through_to_dict() -> None:
    step = make_step(
        index=0,
        action="swap",
        title="Swap USDC -> ETH",
        description="V7-001 roundtrip",
        chain="ethereum",
        wallet="MetaMask",
        protocol="enso",
        simulated_calldata_hash="a" * 64,
        broadcast_calldata_hash="b" * 64,
    )
    data = step.to_dict()
    assert data["simulated_calldata_hash"] == "a" * 64
    assert data["broadcast_calldata_hash"] == "b" * 64


def test_to_dict_omits_hashes_when_unset() -> None:
    # Unstamped legacy plans must not leak `null` keys into the wire
    # payload — adapters that don't compute hashes yet still pass.
    step = make_step(
        index=0,
        action="swap",
        title="legacy",
        description="no hash",
        chain="ethereum",
        wallet="MetaMask",
        protocol="enso",
    )
    data = step.to_dict()
    assert "simulated_calldata_hash" not in data
    assert "broadcast_calldata_hash" not in data


# ----------------------------------------------------------------------
# compute_calldata_hash determinism
# ----------------------------------------------------------------------
def test_compute_calldata_hash_is_stable_for_dict_key_order() -> None:
    a = {"to": "0xabc", "data": "0xdeadbeef", "value": "0"}
    b = {"value": "0", "data": "0xdeadbeef", "to": "0xabc"}
    assert compute_calldata_hash(a) == compute_calldata_hash(b)


def test_compute_calldata_hash_handles_unsigned_tx_dataclass() -> None:
    tx = UnsignedStepTransaction(
        chain_kind="evm",
        chain_id=1,
        to="0xabc",
        data="0xdeadbeef",
        value="0",
    )
    # to_dict() drops None fields, so the dataclass and dict paths must
    # produce identical hashes for adapter-side stamping to work.
    assert compute_calldata_hash(tx) == compute_calldata_hash(tx.to_dict())


def test_compute_calldata_hash_normalizes_hex_string() -> None:
    # `0xABCD` and `abcd` must hash to the same digest — wallets return
    # mixed-case hex and we never want a false mismatch.
    assert compute_calldata_hash("0xABCD") == compute_calldata_hash("abcd")


# ----------------------------------------------------------------------
# assert_calldata_match
# ----------------------------------------------------------------------
def test_assert_calldata_match_passes_on_equal_hashes() -> None:
    # Should be a no-op when hashes match.
    assert_calldata_match("a" * 64, "a" * 64)


def test_assert_calldata_match_normalizes_case_and_prefix() -> None:
    assert_calldata_match("0xABCD", "abcd")
    assert_calldata_match("ABCD", "0xabcd")


def test_assert_calldata_match_raises_on_mismatch() -> None:
    with pytest.raises(CalldataHashMismatchError) as exc:
        assert_calldata_match("a" * 64, "b" * 64, step_id="step_x")
    assert exc.value.step_id == "step_x"
    assert "a" * 64 in str(exc.value)
    assert "b" * 64 in str(exc.value)


def test_assert_calldata_match_raises_on_empty_sim_hash() -> None:
    # Never silently sign a broadcast that wasn't bound to a simulation.
    with pytest.raises(CalldataHashMismatchError):
        assert_calldata_match("", "a" * 64)


def test_assert_calldata_match_raises_on_empty_broadcast_hash() -> None:
    with pytest.raises(CalldataHashMismatchError):
        assert_calldata_match("a" * 64, "")


# ----------------------------------------------------------------------
# State-machine integration — mark_step_status('submitted', ...)
# ----------------------------------------------------------------------
def _plan_with_step(**step_kwargs: object) -> tuple[ExecutionPlanV3, ExecutionStepV3]:
    plan = ExecutionPlanV3.new(title="V7-001", summary="binding test")
    step = make_step(
        index=0,
        action="swap",
        title="Swap",
        description="bind test",
        chain="ethereum",
        wallet="MetaMask",
        protocol="enso",
        **step_kwargs,  # type: ignore[arg-type]
    )
    plan.add_step(step)
    return plan, step


def test_mark_step_status_submitted_with_matching_hashes_succeeds() -> None:
    plan, step = _plan_with_step(
        simulated_calldata_hash="c" * 64,
        broadcast_calldata_hash="c" * 64,
    )
    plan.mark_step_status(step.step_id, "submitted")
    assert step.status == "submitted"


def test_mark_step_status_submitted_with_mismatched_hashes_raises() -> None:
    plan, step = _plan_with_step(
        simulated_calldata_hash="c" * 64,
        broadcast_calldata_hash="d" * 64,
    )
    with pytest.raises(CalldataHashMismatchError):
        plan.mark_step_status(step.step_id, "submitted")
    # State must not advance when the guard fires.
    assert step.status != "submitted"


def test_mark_step_status_submitted_refuses_unstamped_broadcast() -> None:
    # Simulated stamped, broadcast missing → refuse. We never want a
    # broadcast that bypasses the bind check.
    plan, step = _plan_with_step(
        simulated_calldata_hash="c" * 64,
        broadcast_calldata_hash=None,
    )
    with pytest.raises(CalldataHashMismatchError):
        plan.mark_step_status(step.step_id, "submitted")


def test_mark_step_status_submitted_legacy_no_hashes_still_passes() -> None:
    # Pre-V7 plans without either hash continue to work — the check is
    # opt-in by stamping. This guards against a rip-and-replace breaking
    # in-flight execution flows during rollout.
    plan, step = _plan_with_step()
    plan.mark_step_status(step.step_id, "submitted")
    assert step.status == "submitted"
