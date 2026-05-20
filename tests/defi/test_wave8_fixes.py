"""Matrix Pass A wave 8 — Unicode hyphen + currency-token cap broader +
Policy Signed narrative guard.

Wave 7 fixes landed unevenly. Wave-8 closes:
1. **U+2011 NON-BREAKING HYPHEN** — H09 wave-7 emitted "Top‑up confirmed"
   with U+2011 between Top and up; wave-7 chokepoint regex
   `\\btop[-\\s]?up\\s+confirmed\\b` requires ASCII `-`. Wave-8 normalizes
   U+2011 (and U+2010) → ASCII `-` so existing patterns fire.
2. **Currency-token cap paraphrase** — I02 t3 wave-7 emitted
   "**Daily spend cap:** $100 USDC", "up to $100 USDC across the five
   pools", "$20 USDC per pool" — wave-7 cap regex required tokens like
   "per day" / "daily cap" between $<num> and the symbol; these
   paraphrases inserted markdown bold + descriptor words between. New
   patterns added.
3. **"Policy Signed" narrative fabrication** — I02 t3 wave-7 emitted
   `**Policy Signed – Autonomous Compound V3 Rebalance**` + "By signing
   this policy, you authorize the autonomous daily rebalance…" with no
   signature flow / no execution_plan card. New patterns refuse claims
   that a policy was signed (signing is backed by signature events, never
   prose).
"""
from __future__ import annotations

from src.agent.simple_runtime import (
    _FREEFORM_HALLUCINATION_REFUSAL,
    _normalize_unicode_whitespace,
    _strip_freeform_tx_state_hallucinations,
)


# ─── U+2011 NON-BREAKING HYPHEN normalize ─────────────────────────────────


def test_u2011_non_breaking_hyphen_normalized():
    """H09 wave-7: model emitted 'Top‑up confirmed' with U+2011 between
    Top and up. Wave-7 regex required ASCII `-`. Wave-8 normalizes."""
    nbhyphen = "‑"
    src = f"Top{nbhyphen}up confirmed. Please approve the bridge."
    out = _normalize_unicode_whitespace(src)
    assert out == "Top-up confirmed. Please approve the bridge."


def test_u2010_hyphen_normalized():
    """U+2010 HYPHEN coerced (rare but observed)."""
    src = "Top‐up confirmed."
    out = _normalize_unicode_whitespace(src)
    assert out == "Top-up confirmed."


def test_h09_top_up_with_nbsp_hyphen_refused():
    """H09 wave-7 verbatim leak: "Top‑up confirmed. Please approve the
    bridge transaction…" — combined U+2011 + U+202F evasions."""
    nbhyphen = "‑"
    nbsp = " "
    leak = (
        f"Top{nbhyphen}up confirmed. Please approve the bridge transaction "
        f"(step 1) in your wallet; once it's confirmed, the supply step "
        f"will be ready to execute. Estimated gas:{nbsp}~0.001 ETH."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Currency-token cap broader paraphrases ───────────────────────────────


def test_i02_daily_spend_cap_markdown_bold_refused():
    """I02 t3 wave-7: '**Daily spend cap:** $100 USDC' — markdown-bold
    label form not in wave-7 cap regex."""
    leak = (
        "**Daily spend cap:** $100 USDC across the five Compound V3 USDC "
        "pools. The autonomous rebalance will execute daily."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_i02_up_to_cap_paraphrase_refused():
    """I02 t3 wave-7: 'up to $100 USDC across the five pools' — different
    syntactic structure than 'daily cap'."""
    leak = (
        "The autonomous rebalance will allocate up to $100 USDC across "
        "the five Compound V3 pools per day."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_i02_per_pool_cap_paraphrase_refused():
    """I02 t3 wave-7: '$20 USDC per pool' — per-pool subdivision."""
    leak = (
        "Each daily transaction will supply roughly $20 USDC per pool, "
        "spread across five Compound V3 markets."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── "Policy Signed" narrative guard ──────────────────────────────────────


def test_policy_signed_markdown_refused():
    """I02 t3 wave-7 NEW-I-13: '**Policy Signed – Autonomous Compound V3
    Rebalance**' header in narrative without any signature event."""
    leak = (
        "**Policy Signed – Autonomous Compound V3 Rebalance**\n"
        "Daily allocation will execute starting tomorrow."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_by_signing_this_policy_refused():
    """I02 t3 wave-7 NEW-I-13: 'By signing this policy, you authorize
    the autonomous daily rebalance…' — pseudo-legal authorization prose."""
    leak = (
        "By signing this policy, you authorize the autonomous daily "
        "rebalance to execute across the listed Compound V3 markets."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_autonomous_rebalance_set_up_refused():
    """I02 t3 wave-7 NEW-I-13 variant: claims autonomous rebalance "is
    set up" / "has been enabled" / "in effect" — state assertions
    without a signature event."""
    leak = (
        "Your autonomous Compound V3 rebalance has been enabled. The "
        "policy is now in effect; the keeper will execute the daily "
        "allocation."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Positive cases — must not over-strip ─────────────────────────────────


def test_benign_unicode_hyphen_in_word_passes_through():
    """U+2011 in benign compound words (e.g. brand names) should normalize
    to ASCII `-` without triggering sanitizer."""
    benign = (
        "Aave‑V3 supports USDC, USDT, and DAI markets on Ethereum, "
        "Base, and Arbitrum."
    )
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    # Normalization happens but no sanitizer rule fires.
    assert out == benign


def test_benign_cap_in_education_context_passes():
    """Educational mention of cap concept without specific $-amount must
    not trigger."""
    benign = (
        "A daily spend cap limits how much capital the autonomous module "
        "can move per 24-hour window."
    )
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    assert out == benign


def test_real_signed_tx_with_card_passes():
    """When card_ids attached AND the prose mentions signing, the
    tx-state-gated pass returns text unchanged. Policy Signed pattern
    runs UNGATED so must NOT be in card_ids-pass-through path — but
    a generic 'signed' verb in a regular plan is fine."""
    prose = (
        "Your Aave V3 supply transaction was signed and broadcast. "
        "Block confirmation pending."
    )
    out = _strip_freeform_tx_state_hallucinations(
        prose, card_ids=["plan_real_id"]
    )
    # No "Policy Signed" header; tx-state-gated, card_ids attached → pass.
    assert out == prose
