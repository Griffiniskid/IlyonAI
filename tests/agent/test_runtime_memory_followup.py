"""Tests for chat memory and follow-up intent recognition.

These cover the bug reported in the staging UI where:
  Turn 1: "allocate 10kusdc throughout the best pools on solana"
          -> returns allocation + sentinel_matrix + execution_plan cards
  Turn 2 (same session): "Please proceed with the execution"
          -> currently returns a generic starter message instead of
             continuing the prior allocate/plan context.

Both turns are sent as a guest (user_id == 0) with a stable client
session_id (matches what the frontend stores in localStorage).
"""
import json
import uuid

import pytest

from src.agent.simple_runtime import detect_followup_intent, run_simple_turn
from src.storage.agent_chats import append_message, list_messages
from src.storage.database import get_database


class _NoopRouter:
    """Router that should never be invoked when intents fully cover the turn."""

    async def complete(self, **kwargs):  # pragma: no cover - safety net
        raise AssertionError("LLM must not be called when intent routing handles the turn")


def _decode_sse(chunks: list[bytes]) -> dict:
    """Parse SSE wire bytes into {events: [...], cards: [...], final: str}."""
    wire = b"".join(chunks).decode()
    events: list[tuple[str, dict]] = []
    for part in wire.strip().split("\n\n"):
        if not part:
            continue
        lines = part.split("\n")
        ev = next((l[len("event: "):] for l in lines if l.startswith("event: ")), "")
        data = next((l[len("data: "):] for l in lines if l.startswith("data: ")), "")
        try:
            payload = json.loads(data) if data else {}
        except Exception:
            payload = {"raw": data}
        events.append((ev, payload))
    cards = [p for e, p in events if e == "card"]
    final = next((p for e, p in events if e == "final"), {})
    return {"events": events, "cards": cards, "final": final}


@pytest.mark.asyncio
async def test_detect_followup_intent_recognizes_proceed_phrases():
    """Standalone helper: phrases meaning 'execute the prior plan' should be recognised."""
    assert detect_followup_intent("Please proceed with the execution") is not None
    assert detect_followup_intent("proceed") is not None
    assert detect_followup_intent("execute the plan") is not None
    assert detect_followup_intent("go ahead and execute") is not None
    assert detect_followup_intent("yes, proceed") is not None
    # Unrelated messages should not match.
    assert detect_followup_intent("what is the price of SOL?") is None
    assert detect_followup_intent("bridge 100 USDC to Arbitrum") is None


@pytest.mark.asyncio
async def test_guest_session_persists_history_across_turns():
    """Two guest turns sharing the same session_id should both end up in storage."""
    chat_id = f"chat-guest-{uuid.uuid4().hex[:8]}"

    # Turn 1
    async for _ in run_simple_turn(
        message="allocate 10k USDC throughout the best pools on solana",
        session_id=chat_id,
        user_id=0,
        wallet=None,
        tools=[],
        router=_NoopRouter(),
    ):
        pass

    # Turn 2 — same session_id, still guest
    async for _ in run_simple_turn(
        message="Please proceed with the execution",
        session_id=chat_id,
        user_id=0,
        wallet=None,
        tools=[],
        router=_NoopRouter(),
    ):
        pass

    db = await get_database()
    messages = await list_messages(db, chat_id=chat_id)
    roles = [m.role for m in messages]
    contents = [m.content for m in messages]

    assert roles.count("user") == 2, f"expected 2 user messages, got roles={roles}"
    assert "allocate 10k USDC throughout the best pools on solana" in contents
    assert "Please proceed with the execution" in contents


@pytest.mark.asyncio
async def test_proceed_follow_up_replays_prior_allocation_context():
    """Sending 'proceed' after an allocate turn must continue the plan, not reset.

    The prior assistant turn is seeded directly via the storage layer so the
    test does not depend on live tool output. This isolates the memory-recall
    behaviour of run_simple_turn.

    Acceptance:
      - Runtime does not return the generic 'Hello!...could you please clarify'
        starter that was reported in the bug screenshot.
      - Final assistant message references execution / allocation / plan.
    """
    chat_id = f"chat-proceed-{uuid.uuid4().hex[:8]}"
    db = await get_database()

    # Seed prior turn: a typical allocation response containing keywords
    # _maybe_replay_followup looks for.
    await append_message(
        db,
        chat_id=chat_id,
        role="user",
        content="allocate 10k USDC throughout the best pools on solana",
    )
    await append_message(
        db,
        chat_id=chat_id,
        role="assistant",
        content=(
            "Sentinel scoring breakdown:\n"
            "I prepared a 5-step execution plan to allocate $10,000 USDC across "
            "Solana pools (Orca, Raydium, Marinade). Review the full plan, then "
            "sign each step in order."
        ),
    )

    # Turn 2 — the bug under test.
    chunks: list[bytes] = []
    async for chunk in run_simple_turn(
        message="Please proceed with the execution",
        session_id=chat_id,
        user_id=0,
        wallet=None,
        tools=[],
        router=_NoopRouter(),
    ):
        chunks.append(chunk)

    parsed = _decode_sse(chunks)
    final_text = (parsed["final"].get("content") or "").lower()

    # Anti-regression: the broken behaviour returned exactly this starter line.
    assert "could you please clarify" not in final_text, (
        "Runtime returned the generic starter — it lost the prior allocation context.\n"
        f"Final content was:\n{parsed['final'].get('content')}"
    )

    # Forward expectation: the response acknowledges the prior allocation/execution plan.
    assert any(kw in final_text for kw in ("execut", "alloc", "plan", "step")), (
        f"Follow-up response did not reference prior plan; got: {parsed['final'].get('content')}"
    )
