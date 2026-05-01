"""Tests for PlanBlockedFrame schema and SSE event registration."""
import pytest

from src.agent.streaming import StreamCollector, frame_event_name
from src.api.schemas.agent import PlanBlockedFrame


def test_plan_blocked_frame_validates():
    frame = PlanBlockedFrame(
        plan_id="plan-123",
        reasons=["insufficient_funds", "high_slippage"],
    )
    assert frame.plan_id == "plan-123"
    assert frame.reasons == ["insufficient_funds", "high_slippage"]
    assert frame.severity == "critical"


def test_plan_blocked_frame_event_literal():
    frame = PlanBlockedFrame(plan_id="p", reasons=["r"])
    assert frame.event == "plan_blocked"


def test_frame_event_name_plan_blocked():
    frame = PlanBlockedFrame(plan_id="p", reasons=["r"])
    assert frame_event_name(frame) == "plan_blocked"


def test_emit_plan_blocked():
    col = StreamCollector()
    col.emit_plan_blocked("plan-123", ["insufficient_funds"])
    frames = list(col.drain())
    assert len(frames) == 1
    frame = frames[0]
    assert isinstance(frame, PlanBlockedFrame)
    assert frame.plan_id == "plan-123"
    assert frame.reasons == ["insufficient_funds"]
    assert frame.severity == "critical"
    assert frame.event == "plan_blocked"
