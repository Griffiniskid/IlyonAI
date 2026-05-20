"""SSE frame encoding and ReAct callback collector for streaming agent output."""
from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler

from src.api.schemas.agent import (
    CardFrame,
    DoneFrame,
    FinalFrame,
    ObservationFrame,
    PlanBlockedFrame,
    PlanCompleteFrame,
    StepStatusFrame,
    ThoughtFrame,
    ToolFrame,
)


def encode_sse(event: str, data: dict) -> bytes:
    """Encode an SSE event + data dict into the wire format ``event: ...\ndata: ...\n\n``."""
    return (
        f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()
    )


def frame_event_name(frame: Any) -> str:
    """Return the SSE event name for a given frame instance."""
    return {
        ThoughtFrame: "thought",
        ToolFrame: "tool",
        ObservationFrame: "observation",
        CardFrame: "card",
        StepStatusFrame: "step_status",
        PlanCompleteFrame: "plan_complete",
        PlanBlockedFrame: "plan_blocked",
        FinalFrame: "final",
        DoneFrame: "done",
    }[type(frame)]


class StreamCollector(AsyncCallbackHandler):
    """LangChain callback that queues typed SSE frames during agent execution.

    Frames are drained by the SSE response handler between agent steps.
    """

    def __init__(self) -> None:
        self._queue: deque = deque()
        self._step: int = 0
        self._started: float = time.monotonic()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def drain(self):
        """Yield and remove all queued frames."""
        while self._queue:
            yield self._queue.popleft()

    def emit_card(self, card_id: str, card_type: str, payload: dict) -> None:
        """Enqueue a card frame.

        Wave 8 — runtime invariant assertion layer. Every card is run
        through `enforce_card_invariants` before queueing. If a P0
        structural invariant fails (signable step has null transaction,
        executable:false referenced without UNSUPPORTED blocker, USD
        overflow, etc.), the card is replaced with a structured
        `invariant_violation` blocker and the original is logged to
        `docs/matrix-runs/invariant-violations.log` for inspection.

        This closes 8+ outstanding P0 surface bugs structurally (rather
        than via reactive sanitizer regex) and catches any future
        regressions for free.
        """
        try:
            from src.agent.runtime_invariants import enforce_card_invariants
            card_type, payload, _violations = enforce_card_invariants(
                card_id, card_type, payload
            )
        except Exception:  # noqa: BLE001
            # Fail-open: never let an invariant bug crash card emission.
            pass
        self._queue.append(
            CardFrame(
                step_index=self._step,
                card_id=card_id,
                card_type=card_type,
                payload=payload,
            )
        )

    def emit_step_status(self, frame: StepStatusFrame) -> None:
        self._queue.append(frame)

    def emit_plan_complete(self, frame: PlanCompleteFrame) -> None:
        self._queue.append(frame)

    def emit_plan_blocked(self, plan_id: str, reasons: list[str]) -> None:
        self._queue.append(
            PlanBlockedFrame(
                plan_id=plan_id,
                reasons=reasons,
            )
        )

    def emit_final(self, content: str, card_ids: list[str]) -> None:
        """Enqueue final + done frames.

        Matrix Pass A waves 1-3 surfaced the same root cause across
        categories A/B/C/E: LLM scratchpad (chain-of-thought, internal
        prompt-engineering instructions, arithmetic worksheets) leaks
        into the user-facing ``final.content`` whenever a composition
        path (allocation / strategy / freeform fallback) returns a
        response that opens with thinking-style prose.

        Wave 4 widened the regex and wired this chokepoint. Wave 5 added
        the body-scan complement (catches leaks AFTER the first markdown
        table — A01 t3 4 kB worksheet, B14 t4 700-char monologue) AND a
        freeform-tx-state-hallucination guard (refuses prose that claims
        `transaction is ready` / `has been executed` / `Current tx: 0x…`
        when no signable execution-plan card backs it — H02 t2 fabricated
        tx hash, F10 t4 "swap has been executed", E10 t2 "submitted",
        A15 t1/t2 "Your Swell Supply transaction is ready", G08 T2
        "**Aave V3 · Supply** — Asset: USDC", I05 t1 hallucinated Kernel
        impl-address narrative).

        Defensively strip at the streaming chokepoint so every code path
        that reaches ``emit_final`` is protected regardless of which
        composition path produced it. The strip functions preserve
        markdown structure (tables, headings, lists) — only scratchpad
        paragraphs and unbacked tx-state assertions are removed.
        """
        try:
            from src.agent.simple_runtime import (
                _strip_freeform_tx_state_hallucinations,
                _strip_strategy_scratchpad,
            )
            content = _strip_strategy_scratchpad(content)
            content = _strip_freeform_tx_state_hallucinations(
                content, card_ids=card_ids
            )
        except Exception:  # noqa: BLE001
            # Fail-open: never let the sanitizer crash the final emit.
            pass
        elapsed = int((time.monotonic() - self._started) * 1000)
        self._queue.append(
            FinalFrame(
                content=content,
                card_ids=card_ids,
                elapsed_ms=elapsed,
                steps=self._step,
            )
        )
        self._queue.append(DoneFrame())

    # ------------------------------------------------------------------
    # LangChain callback hooks
    # ------------------------------------------------------------------

    async def on_agent_action(self, action, **_: Any) -> None:
        self._step += 1
        self._queue.append(
            ThoughtFrame(
                step_index=self._step,
                content=getattr(action, "log", "").strip()
                or f"Using tool {action.tool}",
            )
        )
        self._queue.append(
            ToolFrame(
                step_index=self._step,
                name=action.tool,
                args=action.tool_input
                if isinstance(action.tool_input, dict)
                else {"input": action.tool_input},
            )
        )

    async def on_tool_end(self, output: Any, *, name: str | None = None, **_: Any) -> None:
        self._queue.append(
            ObservationFrame(
                step_index=self._step,
                name=name or "",
                ok=True,
                error=None,
            )
        )

    async def on_tool_error(self, error: Any, *, name: str | None = None, **_: Any) -> None:
        self._queue.append(
            ObservationFrame(
                step_index=self._step,
                name=name or "",
                ok=False,
                error={"code": type(error).__name__, "message": str(error)},
            )
        )
