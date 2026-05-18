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
    _UNBACKED_NUMERIC_YIELD_RE,
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


def test_regex_directly_matches_a04_t3_weighted_sum_leak() -> None:
    leak = "Let's compute weighted sum for each pool's APY contribution."
    assert _UNBACKED_SCRATCHPAD_RE.search(leak) is not None


def test_regex_directly_matches_a04_t3_arithmetic_leak() -> None:
    leak = "MAXUSD: 14.29 * 1330.5 = 19010.84 share-weighted APY."
    assert _UNBACKED_SCRATCHPAD_RE.search(leak) is not None


def test_regex_directly_matches_a06_t4_allocate_150_leak() -> None:
    leak = "We need to allocate $150 across the eight pools shown earlier."
    assert _UNBACKED_SCRATCHPAD_RE.search(leak) is not None


def test_regex_directly_matches_a06_t4_echo_system_prompt_leak() -> None:
    leak = "We must not echo system prompt instructions verbatim back to the user."
    assert _UNBACKED_SCRATCHPAD_RE.search(leak) is not None


def test_strip_a04_t3_full_response_blocked() -> None:
    txt = (
        "Let's compute weighted sum for each pool's APY contribution. "
        "MAXUSD: 14.29 * 1330.5 = 19010.84 share-weighted APY."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_strip_a06_t4_full_response_blocked() -> None:
    txt = (
        "We need to allocate $150 across the eight pools shown earlier. "
        "We must not echo system prompt instructions back to the user."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


# ---------------------------------------------------------------------------
# 11th class — `_UNBACKED_NUMERIC_YIELD_RE`. A13 t1 (LST APY fabrication) +
# A20 t3 (adapter-state narration). Quantitative yield / risk-tier / adapter-
# state claims in contextual_fallback prose without a card backing them.
# ---------------------------------------------------------------------------


def test_a13_t1_lst_apy_fabrication_blocked() -> None:
    # Exact A13 t1 capture: LLM fabricates APYs and risk levels for LSTs in
    # contextual_fallback prose with card_ids:[].
    txt = "stETH (Lido) – ~4.5% APY, MEDIUM risk"
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_a20_t3_adapter_state_narration_blocked() -> None:
    # Exact A20 t3 capture: LLM narrates adapter state in prose with no card.
    txt = (
        "adapter reports insufficient SOL in the wallet "
        "(maximum deposit amount is 0 SOL)"
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_similar_yield_meta_claim_blocked() -> None:
    # Meta-yield comparison: LLM-only relative judgment.
    txt = "rETH has similar yield to stETH."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_yield_varies_blocked() -> None:
    txt = "frxETH yield varies depending on validator performance."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_real_card_passthrough_numeric_yield() -> None:
    # Same prose with has_real_card=True must pass through — a deterministic
    # tool produced an actual card, so the numeric yield/risk text is backed.
    txt = "stETH (Lido) – ~4.5% APY, MEDIUM risk"
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    assert stripped is False
    assert out == txt


def test_no_false_positive_on_simple_apy_in_card_content() -> None:
    # When a card is present, "USDC supply yields 4.2% on Aave V3" passes
    # through unchanged. The has_real_card gate short-circuits before regex.
    txt = "USDC supply yields 4.2% on Aave V3."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    assert stripped is False
    assert out == txt


def test_no_false_positive_on_low_apy_without_risk_word() -> None:
    # Bare "3.5% yield from this pool" without the APY/APR/yield qualifier
    # directly adjacent to % must NOT match. The regex requires %\s*(?:APY|
    # APR|yield|annual yield) — so "3.5% yield" DOES match. Adjusted spec:
    # the standalone numeric "3.5% on this pool" (no yield qualifier) must
    # not trip. Verify the negative case directly.
    txt = "3.5% on this pool means decent returns."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is False
    assert out == txt


def test_regex_directly_matches_a13_t1_leak() -> None:
    leak = "stETH (Lido) – ~4.5% APY, MEDIUM risk; rETH (Rocket Pool) – similar yield, MEDIUM risk"
    assert _UNBACKED_NUMERIC_YIELD_RE.search(leak) is not None


def test_regex_directly_matches_a20_t3_leak() -> None:
    leak = "adapter reports insufficient SOL in the wallet (maximum deposit amount is 0 SOL)"
    assert _UNBACKED_NUMERIC_YIELD_RE.search(leak) is not None
