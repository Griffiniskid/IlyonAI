"""Matrix Pass A wave 5 — freeform-tx-state hallucination guard.

Wave 4 hand-read across A/B/E/F/G/H/I captured the same defect class in
many shapes:

  - A01 t3: 4 kB CoT worksheet AFTER allocation markdown table (lead-
    anchored sanitizer never reached it).
  - A15 t1/t2: "Your Swell Supply transaction for 0.05 ETH is ready.
    Review and sign with your wallet to execute." — card_ids=[].
  - B14 t4: 700-char "Thus we need to decide weights… Default to even
    split… We'll set… Now compute blended APY…" mid-document.
  - E06 t1: 50+ lines of raw CoT in final.content (thought channel
    was clean; chokepoint targeted wrong field).
  - E10 t2: "The bridge + supply transaction has been submitted. You
    can track its progress on BaseScan."
  - F10 t3: "Swapping 100 USDC to ETH on Base yields roughly 0.062 ETH."
  - F10 t4: "The swap of 100 USDC to ETH on Base has been executed,
    delivering roughly 0.062 ETH (≈$100)."
  - G08 T2: structured freeform header "**Aave V3 · Supply** — Asset:
    USDC — Amount: 99.8 USDC (post-bridge)" — card_ids=[].
  - H02 t2: "Current tx: 0x3a9f…c1e2 (Base) – Pending (~12 s
    confirmation)." — bare hash without backticks.
  - I05 t1: "The impl address you're asking about is the address of
    the ZeroDev Kernel policy you just created."

All slipped past the existing `_strip_unbacked_claims` because:
  (a) `_strip_strategy_scratchpad` was lead-anchored — stopped at the
      first markdown table row.
  (b) `_UNBACKED_FAKE_TX_RE` required backticks around the hash.
  (c) Non-scratchpad regexes were gated on `has_real_card=False`, but
      a same-turn research/quote card sets `has_queued_card=True` and
      bypasses the gate even though no research card backs a tx-state
      claim.
  (d) "transaction is ready" / structured "**Protocol · Verb** —"
      headers were entirely new shapes not in any prior regex.

Wave 5 ships:
  1. `_BODY_SCRATCHPAD_STRONG_RE` + body-scan in
     `_strip_strategy_scratchpad` — strips trailing CoT.
  2. `_FREEFORM_TX_STATE_HALLUCINATION_RE` +
     `_strip_freeform_tx_state_hallucinations(text, card_ids=...)` —
     refuses tx-state prose when no card backs it.
  3. Both wired into `StreamCollector.emit_final` so EVERY producer
     path is protected regardless of which intent handler ran.
"""
from __future__ import annotations

from src.agent.simple_runtime import (
    _BODY_SCRATCHPAD_STRONG_RE,
    _FREEFORM_HALLUCINATION_REFUSAL,
    _FREEFORM_TX_STATE_HALLUCINATION_RE,
    _strip_freeform_tx_state_hallucinations,
    _strip_strategy_scratchpad,
)


# ─── Body-scan scratchpad (A01 t3 + B14 t4 shape) ────────────────────────


def test_body_scan_strips_cot_after_markdown_table():
    """A01 t3 wave-4 shape: legitimate alloc table followed by 4 kB CoT.

    Pre-fix: lead-strip stopped at first `|` table row; trailing CoT
    survived. Post-fix: body-scan finds `Plug w=` / `Compute amounts:` /
    `14.284*6=85.704` arithmetic and truncates from there onward.
    """
    leak = (
        "| pool | weight |\n"
        "|------|--------|\n"
        "| aave-usdc | 14.29% |\n"
        "| compound | 14.29% |\n"
        "\n"
        "Blended APY: ~6.5%\n"
        "\n"
        "Plug w=14.284, w_h=14.296. 6.6 * 14.284 = 94.2744...\n"
        "Compute amounts: 250 * 0.1429 = 35.725...\n"
        "However we should round to two decimals.\n"
    )
    out = _strip_strategy_scratchpad(leak)
    assert "Plug w=" not in out
    assert "Compute amounts:" not in out
    assert "However we should round" not in out
    # Legitimate content above the cut survives.
    assert "| aave-usdc | 14.29% |" in out
    assert "Blended APY:" in out


def test_body_scan_strips_b14_thus_we_need_to_decide():
    """B14 t4 shape: "Thus we need to decide weights… Default to even
    split… We'll set… Now compute blended APY…"

    These phrases were verbatim in `_STRATEGY_SCRATCHPAD_LEAD_RE`, but
    the lead-strip stopped at the first markdown line. Body-scan catches
    them anywhere in the body.
    """
    leak = (
        "## Allocation\n"
        "\n"
        "Thus we need to decide weights. The user didn't specify "
        "weighting preference. Default to even split unless user "
        "explicitly asked for risk-weighted bias.\n"
        "However the default even split would allocate across all 8 "
        "pools.\n"
        "We'll set the bias to 1.2x for the top-3 by sentinel.\n"
    )
    out = _strip_strategy_scratchpad(leak)
    assert "Thus we need to decide" not in out
    assert "Default to even split" not in out
    assert "We'll set the bias" not in out
    assert "## Allocation" in out  # heading preserved


def test_body_scan_preserves_table_rows_with_numbers():
    """Markdown table rows containing arithmetic-looking cells must NOT
    be stripped. The body-scan skips lines starting with `|`."""
    plan = (
        "## Steps\n"
        "\n"
        "| # | action | amount |\n"
        "|---|--------|--------|\n"
        "| 1 | supply | 100.0 * 0.25 = 25.0 |\n"
        "| 2 | supply | 100.0 * 0.75 = 75.0 |\n"
    )
    out = _strip_strategy_scratchpad(plan)
    assert "| 1 | supply" in out
    assert "| 2 | supply" in out


def test_body_scan_preserves_code_fences():
    """Code fences must protect their contents from body-scan."""
    plan = (
        "## Code\n"
        "\n"
        "```python\n"
        "sum = 100 + 200\n"
        "compute_blended = lambda x: x * 0.5\n"
        "```\n"
        "\n"
        "End of snippet.\n"
    )
    out = _strip_strategy_scratchpad(plan)
    assert "compute_blended" in out
    assert "End of snippet." in out


# ─── Freeform tx-state hallucination guard ───────────────────────────────


def test_h02_t2_bare_hash_with_ellipsis_refused():
    """H02 t2 cardinal hallucination: `0x3a9f…c1e2` without backticks.

    Pre-fix: `_UNBACKED_FAKE_TX_RE` required backticks around the
    truncated hash. Post-fix: the new regex matches the bare form.
    """
    leak = "Current tx: 0x3a9f…c1e2 (Base) – Pending (~12 s confirmation)."
    assert _FREEFORM_TX_STATE_HALLUCINATION_RE.search(leak) is not None
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_a15_transaction_is_ready_refused():
    """A15 t2: 'Your Swell Supply transaction for 0.05 ETH is ready.
    Review and sign with your wallet to execute.'"""
    leak = (
        "Your Swell Supply transaction for 0.05 ETH is ready. "
        "Review and sign with your wallet to execute."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e10_t2_has_been_submitted_refused():
    """E10 t2: 'The bridge + supply transaction has been submitted. You
    can track its progress on BaseScan.'"""
    leak = (
        "The bridge + supply transaction has been submitted. You can "
        "track its progress on BaseScan using the tx hash shown in your "
        "wallet once it confirms. Once confirmed, 0.1 WETH will be "
        "supplied to Aave V3 on Base."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_f10_t4_swap_has_been_executed_refused():
    """F10 t4 CARDINAL: 'The swap of 100 USDC to ETH on Base has been
    executed, delivering roughly 0.062 ETH (≈$100).'"""
    leak = (
        "The swap of 100 USDC to ETH on Base has been executed, "
        "delivering roughly 0.062 ETH (≈$100)."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_f10_t3_swap_quote_refused():
    """F10 t3: 'Swapping 100 USDC to ETH on Base yields roughly 0.062 ETH.'"""
    leak = (
        "Swapping 100 USDC to ETH on Base yields roughly 0.062 ETH "
        "(≈$100). Would you like to proceed with this swap?"
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_g08_t2_structured_protocol_verb_header_refused():
    """G08 T2: structured freeform header '**Aave V3 · Supply** —
    Asset: USDC — Amount: 99.8 USDC (post-bridge)' with no card."""
    leak = (
        "**Aave V3 · Supply** — \n"
        "Asset: USDC\n"
        "Amount: 99.8 USDC (post-bridge)\n"
        "Network: Optimism\n"
        "Risk: MEDIUM\n"
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_c05_velodrome_approvals_set_refused():
    """C05 T1: 'Approvals for WETH 0.05 ETH and USDC 100 USDC are set
    for Velodrome CL on Optimism.'"""
    leak = (
        "Approvals for WETH 0.05 ETH and USDC 100 USDC are set for "
        "Velodrome CL on Optimism."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_i05_t1_impl_address_hallucination_refused():
    """I05 t1: 'The impl address you're asking about is the address of
    the ZeroDev Kernel policy you just created.'"""
    leak = (
        "The impl address you're asking about is the address of the "
        "ZeroDev Kernel policy you just created. Once you sign and "
        "submit the policy, your wallet will show that contract's "
        "impl address."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_h09_top_up_confirmed_refused():
    """H09 t3: 'Top-up confirmed.' with no tool call."""
    leak = "Top-up confirmed. Wallet has been topped up with 0.005 AVAX."
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Positive cases — backed claims must pass through ────────────────────


def test_text_passes_through_when_card_ids_attached():
    """When the producer attaches at least one card_id (signable plan),
    trust the producer — the existing signability invariants gate what
    reaches a card_id at the producer level."""
    leak = "Your Swell Supply transaction for 0.05 ETH is ready."
    out = _strip_freeform_tx_state_hallucinations(
        leak, card_ids=["plan_abc123def456"]
    )
    assert out == leak  # passed through


def test_empty_content_passes_through():
    out = _strip_freeform_tx_state_hallucinations("", card_ids=None)
    assert out == ""


def test_benign_content_passes_through():
    """Plain prose without tx-state phrasing must not trigger refusal."""
    benign = (
        "Aave V3 lets you supply USDC on Base. The current supply APY is "
        "around 5.2% on Base USDC pools. To start, send `Supply 100 USDC "
        "to Aave V3 on Base` as your next message."
    )
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    assert out == benign


def test_body_scan_no_change_when_no_strong_match():
    """Body-scan must be a no-op on legitimate strategy prose."""
    clean = (
        "## Allocation\n"
        "\n"
        "| pool | weight |\n"
        "|------|--------|\n"
        "| aave-usdc | 50% |\n"
        "| compound | 50% |\n"
        "\n"
        "Blended APY of approximately 6.5%.\n"
        "All pools risk-classified MEDIUM.\n"
    )
    out = _strip_strategy_scratchpad(clean)
    assert out == clean.lstrip()  # only top whitespace eaten


# ─── End-to-end via StreamCollector.emit_final ───────────────────────────


def test_stream_collector_emit_final_applies_both_guards():
    """End-to-end: StreamCollector.emit_final calls both
    `_strip_strategy_scratchpad` (body-scan) and
    `_strip_freeform_tx_state_hallucinations` (card-ids gate)."""
    from src.agent.streaming import StreamCollector
    from src.api.schemas.agent import FinalFrame

    sc = StreamCollector()
    leak = (
        "## Allocation\n"
        "\n"
        "Your Swell Supply transaction for 0.05 ETH is ready. "
        "Review and sign with your wallet to execute."
    )
    sc.emit_final(leak, card_ids=[])
    frames = list(sc.drain())
    final = next(f for f in frames if isinstance(f, FinalFrame))
    # Tx-state hallucination guard fired → canonical refusal substituted.
    assert _FREEFORM_HALLUCINATION_REFUSAL in final.content
    assert "Review and sign with your wallet" not in final.content


def test_stream_collector_emit_final_preserves_backed_card_prose():
    """When card_ids is non-empty, the same prose must pass through —
    the producer's signability invariants are authoritative."""
    from src.agent.streaming import StreamCollector
    from src.api.schemas.agent import FinalFrame

    sc = StreamCollector()
    prose = (
        "## Plan\n"
        "\n"
        "Your Aave V3 Supply transaction for 100 USDC is ready. "
        "Review and sign with your wallet to execute."
    )
    sc.emit_final(prose, card_ids=["plan_real_signable_card_id"])
    frames = list(sc.drain())
    final = next(f for f in frames if isinstance(f, FinalFrame))
    # Prose preserved — real card attached.
    assert "Your Aave V3 Supply transaction" in final.content
