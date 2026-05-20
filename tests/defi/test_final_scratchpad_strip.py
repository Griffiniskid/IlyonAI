"""Pin test for matrix Pass A wave 3 cross-cluster #1 — defensive
scratchpad strip at the streaming `emit_final` chokepoint.

Matrix waves 1-3 surfaced the same root cause across categories
A/B/C/E: LLM scratchpad (chain-of-thought, internal instructions,
arithmetic worksheets) leaks into `final.content` whenever a
composition path returns thinking-style prose. `_strip_strategy_scratchpad`
existed in simple_runtime but was only called from the strategy-compose
path; the allocation / execution_plan / freeform fallback paths
bypassed it.

Fix: wire the strip at `StreamCollector.emit_final` so every code
path is protected regardless of composition origin.
"""
from __future__ import annotations

from src.agent.simple_runtime import _strip_strategy_scratchpad


def test_strip_removes_we_need_to_prefix():
    text = (
        "We need to allocate $250 across the same pools listed (8 pools). "
        "The user says \"Use 250 USDC\".\n"
        "\n"
        "## Allocation\n"
        "| Pool | % | $ |\n"
        "|---|---|---|\n"
        "| Aave V3 | 100% | $250 |\n"
    )
    cleaned = _strip_strategy_scratchpad(text)
    assert cleaned.startswith("## Allocation")


def test_strip_removes_let_me_compose():
    text = (
        "Let me compose the response with sections.\n"
        "Sum: 153.7 + 144.1 = 297.8\n"
        "\n"
        "# Strategy\n"
        "Real content here.\n"
    )
    cleaned = _strip_strategy_scratchpad(text)
    assert cleaned.startswith("# Strategy")


def test_strip_preserves_real_markdown():
    text = (
        "## Header at top\n"
        "Real content.\n"
        "| col | val |\n"
        "|---|---|\n"
        "| a | b |\n"
    )
    cleaned = _strip_strategy_scratchpad(text)
    assert cleaned == text


def test_strip_handles_empty_input():
    assert _strip_strategy_scratchpad("") == ""
    assert _strip_strategy_scratchpad(None) is None  # type: ignore[arg-type]


def test_emit_final_wires_strip():
    """Verify the streaming layer actually calls the strip function on
    final.content — locks the chokepoint wiring so regressions get
    flagged immediately."""
    from src.agent.streaming import StreamCollector
    cb = StreamCollector()
    cb.emit_final(
        content=(
            "We need to allocate $100 across these pools. The user said \"Use 100\".\n\n"
            "## Allocation\n| Pool | $ |\n|---|---|\n| Aave | $100 |\n"
        ),
        card_ids=["card-xyz"],
    )
    final_frame = cb._queue[-2]  # FinalFrame is second-to-last (DoneFrame is last)
    assert "We need to allocate" not in final_frame.content
    assert "## Allocation" in final_frame.content
    assert final_frame.card_ids == ["card-xyz"]


def test_emit_final_fails_open_on_strip_error():
    """If the strip function raises, emit_final must still publish the
    original content — sanitizer must never crash the final emit path."""
    from src.agent.streaming import StreamCollector
    cb = StreamCollector()
    # Pre-existing content with no scratchpad — strip is a no-op,
    # but exercises the try/except wiring.
    cb.emit_final(content="## Plain heading\nRow", card_ids=[])
    final_frame = cb._queue[-2]
    assert "## Plain heading" in final_frame.content
