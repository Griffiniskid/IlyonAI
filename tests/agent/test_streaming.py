"""Tests for SSE frame encoder and StreamCollector."""
import json

import pytest

from src.agent.streaming import StreamCollector, encode_sse, frame_event_name
from src.api.schemas.agent import (
    DoneFrame,
    FinalFrame,
    ObservationFrame,
    PlanCompleteFrame,
    StepStatusFrame,
    ThoughtFrame,
    ToolFrame,
)


# ---------------------------------------------------------------------------
# encode_sse
# ---------------------------------------------------------------------------


def test_encode_sse_formats_event_and_data():
    raw = encode_sse("thought", {"step_index": 1, "content": "hi"})
    text = raw.decode()
    assert text.startswith("event: thought\n")
    assert "data: " in text
    # Compact JSON (no spaces after separators)
    payload = text.split("data: ", 1)[1].strip()
    parsed = json.loads(payload)
    assert parsed["step_index"] == 1
    assert parsed["content"] == "hi"


def test_encode_sse_produces_bytes():
    result = encode_sse("done", {})
    assert isinstance(result, bytes)


def test_encode_sse_compact_separators():
    raw = encode_sse("x", {"a": 1, "b": 2})
    payload = raw.decode().split("data: ", 1)[1].strip()
    assert " " not in payload.split("data:")[0]  # no spaces in JSON


# ---------------------------------------------------------------------------
# frame_event_name
# ---------------------------------------------------------------------------


def test_frame_event_name_thought():
    assert frame_event_name(ThoughtFrame(step_index=1, content="x")) == "thought"


def test_frame_event_name_done():
    assert frame_event_name(DoneFrame()) == "done"


def test_frame_event_name_step_status_and_plan_complete():
    assert frame_event_name(StepStatusFrame(plan_id="p", step_id="s", status="ready", order=1)) == "step_status"
    assert frame_event_name(PlanCompleteFrame(plan_id="p", status="aborted")) == "plan_complete"


# ---------------------------------------------------------------------------
# StreamCollector — step_index monotonicity
# ---------------------------------------------------------------------------


class _FakeAction:
    def __init__(self, tool: str, tool_input, log: str = ""):
        self.tool = tool
        self.tool_input = tool_input
        self.log = log


@pytest.mark.asyncio
async def test_collector_monotonic_step_index():
    col = StreamCollector()

    await col.on_agent_action(_FakeAction("t1", {"q": "a"}))
    await col.on_agent_action(_FakeAction("t2", {"q": "b"}))

    frames = list(col.drain())
    assert len(frames) == 4  # 2 Thought + 2 Tool per action
    steps = [f.step_index for f in frames]
    assert steps == [1, 1, 2, 2]


# ---------------------------------------------------------------------------
# StreamCollector — observation carries tool name + ok
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observation_carries_tool_name_and_ok():
    col = StreamCollector()
    await col.on_agent_action(_FakeAction("search", {"q": "sol"}))
    # drain the Thought + Tool frames
    list(col.drain())

    await col.on_tool_end("result text", name="search")
    obs_frames = list(col.drain())
    assert len(obs_frames) == 1
    obs = obs_frames[0]
    assert isinstance(obs, ObservationFrame)
    assert obs.name == "search"
    assert obs.ok is True
    assert obs.error is None


# ---------------------------------------------------------------------------
# StreamCollector — error carries code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_carries_code():
    col = StreamCollector()
    await col.on_agent_action(_FakeAction("bad_tool", {}))
    list(col.drain())

    await col.on_tool_error(ValueError("boom"), name="bad_tool")
    obs_frames = list(col.drain())
    assert len(obs_frames) == 1
    obs = obs_frames[0]
    assert obs.ok is False
    assert obs.error is not None
    assert obs.error.code == "ValueError"
    assert obs.error.message == "boom"


# ---------------------------------------------------------------------------
# StreamCollector — emit_final + emit_card
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_final_includes_done():
    col = StreamCollector()
    col.emit_final("answer", ["c1"])
    frames = list(col.drain())
    assert len(frames) == 2
    assert isinstance(frames[0], FinalFrame)
    assert frames[0].content == "answer"
    assert frames[0].card_ids == ["c1"]
    assert isinstance(frames[1], DoneFrame)


def test_emit_card_frame():
    col = StreamCollector()
    col.emit_card("id1", "pool", {"protocol": "ray"})
    frames = list(col.drain())
    assert len(frames) == 1
    assert frames[0].card_id == "id1"
    assert frames[0].card_type == "pool"
