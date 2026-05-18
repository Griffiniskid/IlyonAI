"""V7-072 — Pin test for the global "LLM never emits calldata" runtime gate.

Verifies that `_strip_unbacked_claims` from src/agent/simple_runtime.py:

  1. STRIPS prose containing a 0x-prefixed hex blob ≥80 chars when
     there is no real card backing the response (the V7-072 gate hit).
  2. PASSES the same blob through unchanged when has_real_card=True —
     real calldata DOES legitimately ship inside a deterministic
     UnsignedStepTransaction surfaced via a backing card.
  3. Still triggers the legacy 120+ fabricated_calldata path on the
     longest blobs (regression — V7-072 must not weaken the existing
     guard).
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import (
    _UNBACKED_LLM_CALLDATA_GATE_RE,
    _strip_unbacked_claims,
)


# A 80-hex-char 0x blob (40 bytes — bigger than an address, smaller
# than the legacy 120-char gate). Exactly the medium-length calldata
# leak V7-072 is designed to catch.
_BLOB_80 = "0x" + ("a1b2c3d4" * 10)  # 80 hex chars
# A 120-hex-char blob — should ALSO trigger the legacy fabricated_calldata path.
_BLOB_120 = "0x" + ("deadbeef" * 15)  # 120 hex chars


def test_v7_072_gate_regex_matches_80_hex_chars():
    """The V7-072 gate regex catches medium-length calldata blobs."""
    assert _UNBACKED_LLM_CALLDATA_GATE_RE.search(_BLOB_80) is not None


def test_v7_072_gate_regex_skips_short_addresses():
    """40-hex addresses (without context) must NOT be matched by the
    V7-072 gate — that's the address regex's job (with context)."""
    # Bare 40-hex address, well under the 80-char threshold.
    addr_only = "Spender 0x" + ("a" * 40)
    assert _UNBACKED_LLM_CALLDATA_GATE_RE.search(addr_only) is None


def test_v7_072_strips_medium_calldata_when_no_card():
    """80-hex blob in prose without a card → sanitizer refuses."""
    prose = f"The encoded calldata you need is {_BLOB_80}. Submit it via your wallet."
    cleaned, stripped = _strip_unbacked_claims(prose, has_real_card=False)
    assert stripped is True
    # The refusal copy mentions the deterministic verb form.
    assert "deterministic" in cleaned.lower() or "explicit verb" in cleaned.lower()
    # And the original calldata blob is gone from the cleaned output.
    assert _BLOB_80 not in cleaned


def test_v7_072_passes_calldata_through_when_real_card_present():
    """Same 80-hex blob with has_real_card=True → not stripped.

    Real cards legitimately surface UnsignedStepTransaction.data, and
    the sanitizer must not corrupt a backed response.
    """
    prose = f"Plan ready. Calldata pinned at {_BLOB_80}."
    cleaned, stripped = _strip_unbacked_claims(prose, has_real_card=True)
    assert stripped is False
    assert cleaned == prose


def test_legacy_120_char_path_still_fires():
    """The pre-existing fabricated_calldata regex (120+ hex chars)
    must still trigger — V7-072 is additive, not a replacement."""
    prose = f"Here's the calldata: {_BLOB_120}"
    cleaned, stripped = _strip_unbacked_claims(prose, has_real_card=False)
    assert stripped is True
    assert _BLOB_120 not in cleaned


def test_v7_072_no_false_positive_on_short_prose():
    """Generic refusal copy without any calldata must pass through."""
    prose = "I can't execute that — please use an explicit verb form."
    cleaned, stripped = _strip_unbacked_claims(prose, has_real_card=False)
    assert stripped is False
    assert cleaned == prose


def test_v7_072_no_false_positive_on_empty():
    """Empty string is a no-op (defensive — runtime occasionally calls
    with cleaned=='' after upstream stripping)."""
    cleaned, stripped = _strip_unbacked_claims("", has_real_card=False)
    assert stripped is False
    assert cleaned == ""
