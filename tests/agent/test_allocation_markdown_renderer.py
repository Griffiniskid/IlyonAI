"""Pin tests for `src.agent.render.allocation_markdown`.

Background: Pass A F-category hand-read (F04/t4, F05/t3, enso-12/t2) found
that the markdown allocation table rendered 8 rows × $12.50 while the
emitted `allocation` card carried 5 positions × $20. Dual-reducer
disagreement. These tests pin the contract: the markdown renderer iterates
positions in the EMITTED card payload (the source of truth) — never
re-derives N or weights from raw candidates.
"""
from __future__ import annotations

import re

import pytest

from src.agent.render.allocation_markdown import (
    render_allocation_section,
    render_allocation_table,
    replace_allocation_table_in_narrative,
)


def _payload(n: int) -> dict:
    """Build a minimal AllocationPayload-dict with `n` positions.

    Each position carries an even weight summing to 100, $ amounts that
    match the weight, and distinct protocol/asset/chain values so the
    renderer's output is deterministic for assertions.
    """
    even = 100 // n
    weights = [even] * n
    weights[0] += 100 - sum(weights)
    positions = []
    for i, w in enumerate(weights, start=1):
        positions.append(
            {
                "rank": i,
                "protocol": f"proto-{i}",
                "asset": f"ASSET{i}",
                "chain": "ethereum" if i % 2 == 1 else "solana",
                "apy": f"{(i + 1) * 1.5:.1f}%",
                "sentinel": 70 + i,
                "risk": "medium",
                "fit": "balanced",
                "weight": w,
                "usd": f"${100 * w / 100:.0f}",
                "tvl": "$1M",
                "router": "Enso",
                "safety": 70,
                "durability": 70,
                "exit": 70,
                "confidence": 70,
                "flags": [],
            }
        )
    blended = sum(float(p["apy"].rstrip("%")) * p["weight"] / 100.0 for p in positions)
    return {
        "positions": positions,
        "total_usd": "$100",
        "blended_apy": f"{blended:.2f}%",
        "chains": 2 if n >= 2 else 1,
        "weighted_sentinel": 75,
        "risk_mix": {"low": 0, "medium": n, "high": 0},
        "combined_tvl": f"${n}M",
    }


def _count_data_rows(table: str) -> int:
    """Count rows that start with `| <integer> |` — the actual data rows."""
    return sum(1 for ln in table.splitlines() if re.match(r"^\|\s*\d+\s*\|", ln))


# --- Pin contract: N rows in markdown == N positions in payload ----------


def test_render_n5_emits_exactly_5_rows():
    """N=5 → exactly 5 data rows. This is the F04/F05 regression pin."""
    payload = _payload(5)
    table = render_allocation_table(payload)
    assert _count_data_rows(table) == 5, (
        f"Expected 5 data rows for N=5 payload, got:\n{table}"
    )


def test_render_n3_emits_exactly_3_rows():
    payload = _payload(3)
    table = render_allocation_table(payload)
    assert _count_data_rows(table) == 3


def test_render_n8_emits_exactly_8_rows():
    """Confirms renderer iterates payload positions — N=8 → 8 rows."""
    payload = _payload(8)
    table = render_allocation_table(payload)
    assert _count_data_rows(table) == 8


def test_render_empty_payload_returns_empty_string():
    assert render_allocation_table({"positions": []}) == ""
    assert render_allocation_table(None) == ""
    assert render_allocation_table([]) == ""


# --- Pin: dollar amounts & weights come from payload, not re-derived ------


def test_dollar_amounts_match_payload_not_recomputed():
    """If the payload says $20 for a 20%-weight position, the row must say
    $20 — never $12.50 derived from a different N.
    """
    payload = _payload(5)
    # Force a known dollar value distinct from naive N=8 reduction
    for pos in payload["positions"]:
        pos["usd"] = "$20"
    table = render_allocation_table(payload)
    # All 5 data rows must say $20 — never $12.50
    assert table.count("$20") == 5
    assert "$12.50" not in table
    assert "$12" not in table  # No N=8 leftovers


def test_weights_come_from_payload():
    payload = _payload(5)
    # Hand-set a ladder weight set: 35/20/20/15/10
    ladder = [35, 20, 20, 15, 10]
    for w, pos in zip(ladder, payload["positions"]):
        pos["weight"] = w
        pos["usd"] = f"${w}"
    table = render_allocation_table(payload)
    for w in ladder:
        assert f"| {w}% |" in table, f"weight {w} missing from rendered table"


# --- Pin: section helper carries summary line from payload ----------------


def test_section_summary_quotes_payload_blended_apy_and_total():
    payload = _payload(5)
    payload["total_usd"] = "$1,000"
    payload["blended_apy"] = "~7.4%"
    section = render_allocation_section(payload)
    assert "## Allocation" in section
    assert "$1,000" in section
    assert "~7.4%" in section
    assert _count_data_rows(section) == 5


# --- Pin: surgical narrative rewriter replaces old LLM table --------------


def test_replace_in_narrative_swaps_dual_reducer_table():
    """Simulates the F04/F05 wire-up: LLM narrative has 8 rows × $12.50,
    the card payload has 5 positions × $20. After replacement the table
    must reflect the payload, not the LLM's hallucination.
    """
    bad_narrative = (
        "## Allocation\n"
        "| # | Protocol · Pair (chain) | Weight % | $ Amount | APY | Risk |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | binance-staked-eth · WBETH (Ethereum) | 12.5% | $12.50 | 2.4% | LOW |\n"
        "| 2 | lido · stETH (Ethereum) | 12.5% | $12.50 | 3.1% | LOW |\n"
        "| 3 | aave-v3 · USDC (Ethereum) | 12.5% | $12.50 | 4.0% | LOW |\n"
        "| 4 | aave-v3 · USDT (Ethereum) | 12.5% | $12.50 | 4.2% | LOW |\n"
        "| 5 | compound-v3 · USDC (Ethereum) | 12.5% | $12.50 | 3.9% | LOW |\n"
        "| 6 | morpho · USDC (Ethereum) | 12.5% | $12.50 | 5.0% | LOW |\n"
        "| 7 | yearn · DAI (Ethereum) | 12.5% | $12.50 | 6.2% | MEDIUM |\n"
        "| 8 | aave-v3 · WBTC (Ethereum) | 12.5% | $12.50 | 0.0% | LOW |\n\n"
        "The equally weighted portfolio expects a blended APY of approximately **1.98%**.\n"
    )
    payload = _payload(5)
    for pos in payload["positions"]:
        pos["usd"] = "$20"
        pos["weight"] = 20

    fixed = replace_allocation_table_in_narrative(bad_narrative, payload)

    # Pin: the rendered output has exactly 5 data rows, not 8.
    assert _count_data_rows(fixed) == 5, (
        f"Expected 5 data rows after replacement, got {_count_data_rows(fixed)}:\n{fixed}"
    )
    # Pin: no $12.50 leftover from the LLM's hallucinated reducer.
    assert "$12.50" not in fixed
    # Pin: each row shows $20 from the card payload.
    assert fixed.count("$20") >= 5


def test_replace_in_narrative_appends_when_no_table_present():
    """No allocation table in narrative → prepend a fresh one sourced
    from the payload (we must NEVER ship a narrative without the table
    when the card has positions).
    """
    narrative = "## Strategy\nLook for stables on L2.\n"
    payload = _payload(3)
    fixed = replace_allocation_table_in_narrative(narrative, payload)
    assert "## Allocation" in fixed
    assert _count_data_rows(fixed) == 3
    # Original content preserved
    assert "Look for stables on L2." in fixed


def test_replace_in_narrative_empty_payload_returns_narrative_untouched():
    narrative = "## Strategy\nFoo bar.\n"
    fixed = replace_allocation_table_in_narrative(narrative, {"positions": []})
    assert fixed == narrative


def test_replace_in_narrative_does_not_duplicate_table():
    """Idempotent — running twice does not produce two allocation tables."""
    payload = _payload(5)
    once = replace_allocation_table_in_narrative("seed prose", payload)
    twice = replace_allocation_table_in_narrative(once, payload)
    # Count of data-rows must match payload N, not 2*N.
    assert _count_data_rows(twice) == 5


# --- Pin: pydantic model input works too ---------------------------------


def test_render_accepts_pydantic_model_input():
    """The runtime emits AllocationPayload via Pydantic — the renderer must
    accept either the model or its dict dump.
    """
    from src.api.schemas.agent import AllocationPayload, AllocationPosition

    positions = [
        AllocationPosition(
            rank=i + 1,
            protocol=f"proto-{i+1}",
            asset=f"ASSET{i+1}",
            chain="eth",
            apy="3.0%",
            sentinel=80,
            risk="low",
            fit="balanced",
            weight=20,
            usd="$20",
            tvl="$1M",
            router="Enso",
            safety=80,
            durability=80,
            exit=80,
            confidence=80,
            flags=[],
        )
        for i in range(5)
    ]
    payload = AllocationPayload(
        positions=positions,
        total_usd="$100",
        blended_apy="3.0%",
        chains=1,
        weighted_sentinel=80,
        risk_mix={"low": 5, "medium": 0, "high": 0},
        combined_tvl="$5M",
    )
    table = render_allocation_table(payload)
    assert _count_data_rows(table) == 5
    assert table.count("$20") == 5
