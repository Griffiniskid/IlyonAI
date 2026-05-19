"""Pin test for BUG-E-002 — matrix Pass A wave 1 surfaced that
build_yield_execution_plan was passing the literal `"guest"` sentinel to
deBridge DLN /create-tx as senderAddress + dstChainTokenOutRecipient,
which DLN rejected with HTTP 400 (mozilla.org docs URL leaked back to
the user). The fix gates the call on an EVM-shaped address; absent that,
it emits a WALLET_CHAIN_MISMATCH blocker via the canonical
ExecutionBlocker pipeline.

This pin is presence-based (the full code path needs a heavy mock fixture
to exercise end-to-end) but locks the three key contract points:
  - the guard pattern is wired
  - the canonical blocker code is used (so the normalizer pipeline accepts it)
  - the legacy 'guest' literal is not forwarded to deBridge unconditionally
"""
from __future__ import annotations

import pathlib
import re


_BUILD_PLAN_SRC = pathlib.Path(
    "src/agent/tools/build_yield_execution_plan.py"
).read_text(encoding="utf-8")


def test_guest_guard_pattern_wired():
    """The guard checks an EVM-address shape and the 'guest' sentinel
    before calling bridge.create_order_encoded."""
    # The fix introduces a `_looks_like_evm_addr` local before the
    # create_order_encoded call.
    assert "_looks_like_evm_addr" in _BUILD_PLAN_SRC, (
        "BUG-E-002 guard removed — re-check build_yield_execution_plan.py "
        "before create_order_encoded callsite."
    )


def test_guest_guard_emits_wallet_chain_mismatch_blocker():
    """Per the canonical KNOWN_BLOCKER_CODES + alias table, the
    closest-fit code is WALLET_CHAIN_MISMATCH (until a distinct
    WALLET_NOT_CONNECTED code lands). The guard must use this exact
    string so the normalizer pipeline accepts it."""
    # Find the guard's emit-block + ensure it carries the canonical code.
    # The block introduces _looks_like_evm_addr; the blocker emission
    # within the same `if (not _looks_like_evm_addr) ...` arm must
    # reference WALLET_CHAIN_MISMATCH.
    guard_match = re.search(
        r"_looks_like_evm_addr.*?(?=try:\s*\n\s*order_tx)",
        _BUILD_PLAN_SRC,
        re.DOTALL,
    )
    assert guard_match is not None, "guard block not found before create_order_encoded"
    assert "WALLET_CHAIN_MISMATCH" in guard_match.group(0), (
        "guard does not emit canonical WALLET_CHAIN_MISMATCH code"
    )


def test_create_order_encoded_call_is_inside_guarded_branch():
    """The deBridge create_order_encoded call must be reached ONLY after
    the guest-guard early-return. Locked by source-order check: the
    string `_looks_like_evm_addr` must appear before `create_order_encoded`."""
    guard_idx = _BUILD_PLAN_SRC.find("_looks_like_evm_addr")
    call_idx = _BUILD_PLAN_SRC.find("await bridge.create_order_encoded(")
    assert guard_idx > 0
    assert call_idx > 0
    assert guard_idx < call_idx, (
        "create_order_encoded callsite is no longer behind the guest-guard"
    )
