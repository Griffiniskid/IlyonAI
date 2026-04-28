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
        """Enqueue a card frame."""
        self._queue.append(
            CardFrame(
                step_index=self._step,
                card_id=card_id,
                card_type=card_type,
                payload=payload,
            )
        )

    def emit_final(self, content: str, card_ids: list[str]) -> None:
        """Enqueue final + done frames."""
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
