"""Pin tests for the chain-of-thought scratchpad sanitizer.

Surfaced by A01 turn 3 live-matrix hand-read: the USDC allocation turn emitted
raw model planning monologue ("We need to allocate $250 across the same
pools... Compute each amount: 250 * (1/7) = 35.71") as user-facing prose. The
existing 9 `_UNBACKED_*` patterns covered fake card impersonation, fake tx
hashes, calldata, addresses, metrics, state assertions, URLs, selector+args,
and LLM calldata blobs — but NOT first-person planning narration.

`_UNBACKED_SCRATCHPAD_RE` plugs that gap. Refuses chain-of-thought leak when
no real card backs the response; passes through when a deterministic tool did
emit a card (dev trace is fine then).
"""
from __future__ import annotations

from src.agent.simple_runtime import (
    _UNBACKED_SCRATCHPAD_RE,
    _strip_unbacked_claims,
)


REFUSAL_MARKER = "I can't confirm that action without a deterministic Sentinel"


def test_we_need_to_allocate_stem_stripped() -> None:
    txt = "We need to allocate $250 across the same pools as before."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_inline_arithmetic_compute_step_stripped() -> None:
    txt = "Compute each amount: 250 * (1/7) = 35.71 USDC per pool."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_lets_break_this_down_stripped() -> None:
    txt = "Let's break this down step by step: first we identify each pool."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_first_we_identify_stripped() -> None:
    txt = "First, we identify the seven highest-APY pools on Base."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_scratchpad_with_real_card_passthrough() -> None:
    # When a deterministic tool produced an actual card, the dev trace is fine.
    txt = "We need to allocate $250 across the same pools. Compute 250 * (1/7) = 35.71."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    assert stripped is False
    assert out == txt


def test_normal_user_facing_prose_passthrough() -> None:
    # Real defi research result — must not be stripped.
    txt = "USDC supply yields 4.2% on Aave V3 Base."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is False
    assert out == txt


def test_bare_short_we_or_lets_does_not_false_match() -> None:
    # Conservative requirement: planning stem needs ≥1 substantive follow-on
    # word. Bare two-word sentences must not trip the regex.
    assert _UNBACKED_SCRATCHPAD_RE.search("Let's go.") is None
    assert _UNBACKED_SCRATCHPAD_RE.search("We can.") is None


def test_step_n_colon_pattern_stripped() -> None:
    txt = "Step 1: divide the total by seven pools."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_regex_directly_matches_a01_t3_leak() -> None:
    # The exact A01 t3 leak fragment.
    leak = "We need to allocate $250 across the same pools... Compute each amount: 250 * (1/7) = 35.71"
    assert _UNBACKED_SCRATCHPAD_RE.search(leak) is not None
