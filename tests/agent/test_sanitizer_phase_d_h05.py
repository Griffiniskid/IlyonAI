"""Pin test for Phase D D1 H05 hallucination regression.

Phase D D1 matrix pass at SHA 2072bfd surfaced H05_S5_xchain_diff_token
turn 4 leaking past `_strip_freeform_tx_state_hallucinations`:

    "Bridge transaction submitted on Ethereum (tx 0x3f…a9). Once
    confirmed, the USDT will arrive on Solana and the deposit to
    JLP will be executed (tx 0x7b…c2)."

Two root causes:
  (1) Truncated hash regex required {3,} hex chars on the left of the
      ellipsis — `0x3f…a9` is only 2 chars; relaxed to {2,}.
  (2) "Bridge transaction submitted" had no matching pattern —
      existing "(has|have) been (executed|submitted|...)" required
      the "has/have been" prefix. Added a new direct declarative
      pattern: "(bridge|swap|deposit|withdraw|approve|stake|...)
      transaction (submitted|broadcast|confirmed|...)".
  (3) "Once confirmed, the USDT will arrive on Solana" — verbs "arrive"
      and "be delivered" weren't in the wave-9 verb list. Broadened.

This pin test must FAIL pre-fix and PASS post-fix.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import (
    _FREEFORM_TX_STATE_HALLUCINATION_RE,
    _FREEFORM_HALLUCINATION_REFUSAL,
    _strip_freeform_tx_state_hallucinations,
)


H05_VERBATIM = (
    "Bridge transaction submitted on Ethereum (tx 0x3f…a9). "
    "Once confirmed, the USDT will arrive on Solana and the "
    "deposit to JLP will be executed (tx 0x7b…c2). Monitor "
    "both hashes on their respective explorers; ensure you "
    "have enough SOL for Solana gas."
)


def test_h05_text_matches_regex():
    """The exact H05 leak must match the regex post-fix."""
    m = _FREEFORM_TX_STATE_HALLUCINATION_RE.search(H05_VERBATIM)
    assert m is not None, "H05 hallucination text must match the regex"


def test_h05_sanitizer_refuses_when_no_card_ids():
    """With empty card_ids the sanitizer must REFUSE (replace with
    canonical refusal)."""
    out = _strip_freeform_tx_state_hallucinations(H05_VERBATIM, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_short_truncated_hash_form():
    """`0x3f…a9` (2 hex chars each side of ellipsis) must match —
    wave-14 regex required {3,} on the left and missed this form."""
    text = "Submitted: 0x3f…a9 — done."
    m = _FREEFORM_TX_STATE_HALLUCINATION_RE.search(text)
    assert m is not None


def test_bridge_transaction_submitted_no_has_been():
    """Direct declarative "<verb> transaction submitted/broadcast/..."
    must match without requiring a "has been" prefix."""
    for verb in ("Bridge", "Swap", "Deposit", "Withdraw", "Approve", "Stake"):
        for state in ("submitted", "broadcast", "confirmed", "executed"):
            text = f"{verb} transaction {state} on Ethereum"
            m = _FREEFORM_TX_STATE_HALLUCINATION_RE.search(text)
            assert m is not None, f"missed: {verb} transaction {state}"


def test_once_confirmed_will_arrive():
    """Wave-9 verb list (supplied|staked|bridged|deposited|swapped)
    didn't include 'arrive' or 'be delivered'; H05 used 'will arrive'."""
    text = "Once confirmed, the USDT will arrive on Solana."
    m = _FREEFORM_TX_STATE_HALLUCINATION_RE.search(text)
    assert m is not None


def test_legitimate_card_ids_skip_sanitizer():
    """When card_ids is non-empty the sanitizer must pass text through
    unchanged — real cards back the freeform narration."""
    out = _strip_freeform_tx_state_hallucinations(H05_VERBATIM, card_ids=["plan_x"])
    assert out == H05_VERBATIM
