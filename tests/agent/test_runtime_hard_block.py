"""Tests for the critical-shield hard-block in agent runtimes.

When a tool envelope's Shield is critical (verdict=SCAM or grade=F),
the runtime must emit a plan_blocked SSE frame and skip the signing flow.
"""
import json

import pytest

from src.api.schemas.agent import ShieldBlock, ToolEnvelope


@pytest.mark.asyncio
async def test_simple_runtime_emits_plan_blocked_for_critical_envelope():
    """When a tool envelope's Shield is critical, the runtime helper must
    yield a plan_blocked-shaped payload."""
    from src.agent.simple_runtime import _emit_plan_blocked_if_critical

    env = ToolEnvelope(
        ok=True,
        data={},
        card_type="swap_quote",
        card_id="swap-123",
        card_payload={"router": "UnknownDangerousRouter"},
        shield=ShieldBlock(
            verdict="SCAM",
            grade="F",
            reasons=["Known malicious destination"],
        ),
    )

    frames = list(_emit_plan_blocked_if_critical(env, plan_id="plan-x"))
    assert frames, "expected at least one plan_blocked frame"
    payload = frames[0]
    assert payload["plan_id"] == "plan-x"
    assert payload["severity"] == "critical"
    assert "Known malicious destination" in payload["reasons"]


def test_is_critical_shield_detects_grade_f():
    from src.agent.simple_runtime import _is_critical_shield

    env = ToolEnvelope(
        ok=True,
        data={},
        card_id="x",
        shield=ShieldBlock(verdict="DANGEROUS", grade="F", reasons=["bad"]),
    )
    assert _is_critical_shield(env) is True


def test_is_critical_shield_detects_scam_verdict():
    from src.agent.simple_runtime import _is_critical_shield

    env = ToolEnvelope(
        ok=True,
        data={},
        card_id="x",
        shield=ShieldBlock(verdict="SCAM", grade="D", reasons=["bad"]),
    )
    assert _is_critical_shield(env) is True


def test_is_critical_shield_returns_false_for_safe():
    from src.agent.simple_runtime import _is_critical_shield

    env = ToolEnvelope(
        ok=True,
        data={},
        card_id="x",
        shield=ShieldBlock(verdict="SAFE", grade="A", reasons=[]),
    )
    assert _is_critical_shield(env) is False


def test_is_critical_shield_returns_false_when_shield_missing():
    from src.agent.simple_runtime import _is_critical_shield

    env = ToolEnvelope(ok=True, data={}, card_id="x", shield=None)
    assert _is_critical_shield(env) is False


def test_emit_plan_blocked_yields_nothing_for_non_critical():
    from src.agent.simple_runtime import _emit_plan_blocked_if_critical

    env = ToolEnvelope(
        ok=True,
        data={},
        card_id="x",
        shield=ShieldBlock(verdict="CAUTION", grade="C", reasons=["minor"]),
    )
    frames = list(_emit_plan_blocked_if_critical(env, plan_id="plan-y"))
    assert frames == []


@pytest.mark.asyncio
async def test_simple_runtime_short_circuits_on_critical_shield(monkeypatch):
    """run_ephemeral_turn must emit a plan_blocked SSE frame and skip
    card emission when a tool returns a critical-shield envelope."""
    from src.agent import simple_runtime as sr

    # Force intent to a known tool name so the tool branch executes.
    monkeypatch.setattr(
        sr, "detect_intent", lambda message: ("simulate_swap", {"token_in": "X"})
    )

    class FakeTool:
        name = "simulate_swap"

        async def ainvoke(self, _args):
            return ToolEnvelope(
                ok=True,
                data={"router": "Bad"},
                card_type="swap_quote",
                card_id="swap-block-1",
                card_payload={"router": "Bad"},
                shield=ShieldBlock(
                    verdict="SCAM",
                    grade="F",
                    reasons=["Malicious router detected"],
                ),
            )

    frames: list[bytes] = []
    async for chunk in sr.run_ephemeral_turn(
        router=None, tools=[FakeTool()], message="swap 1 ETH for X"
    ):
        frames.append(chunk)

    text = b"".join(frames).decode()
    assert "event: plan_blocked" in text
    # The plan_blocked data line must mention the shield reason.
    assert "Malicious router detected" in text
    # No card frame should leak through.
    assert "event: card" not in text
