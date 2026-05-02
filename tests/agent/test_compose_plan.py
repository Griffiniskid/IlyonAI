"""Tests for compose_plan tool."""
from __future__ import annotations

import pytest

from src.agent.tools.compose_plan import compose_plan
from src.agent.tools._base import ToolCtx


class DummyServices:
    pass


@pytest.fixture
def ctx():
    return ToolCtx(services=DummyServices(), user_id=1, wallet=None)


@pytest.mark.asyncio
async def test_compose_plan_returns_execution_plan_v2_card(ctx):
    intent = {
        "title": "Swap and stake",
        "steps": [
            {
                "action": "swap",
                "params": {
                    "token_in": "USDC",
                    "token_out": "ETH",
                    "amount": "100",
                    "chain_id": 1,
                },
            },
            {
                "action": "stake",
                "params": {
                    "token": "ETH",
                    "amount": "100",
                    "chain_id": 1,
                },
            },
        ],
    }

    result = await compose_plan(ctx, intent=intent)

    assert result.ok is True
    assert result.card_type == "execution_plan_v2"
    assert result.card_payload is not None
    assert result.card_payload["title"] == "Swap and stake"
    # approve (swap) + swap + stake = 3
    assert result.card_payload["total_steps"] == 3
    assert len(result.card_payload["steps"]) == 3
    assert result.card_payload["risk_gate"] in {"clear", "soft_warn", "hard_block"}
    assert "plan_id" in result.card_payload


@pytest.mark.asyncio
async def test_compose_plan_validates_intent_dict(ctx):
    result = await compose_plan(ctx, intent="not a dict")
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "bad_intent"


@pytest.mark.asyncio
async def test_compose_plan_validates_steps_list(ctx):
    result = await compose_plan(ctx, intent={"title": "test", "steps": "not a list"})
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "bad_intent"


@pytest.mark.asyncio
async def test_compose_plan_validates_step_structure(ctx):
    result = await compose_plan(ctx, intent={
        "title": "test",
        "steps": [{"params": {}}],  # missing "action"
    })
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "bad_intent"


@pytest.mark.asyncio
async def test_compose_plan_empty_steps(ctx):
    result = await compose_plan(ctx, intent={"title": "Empty", "steps": []})
    assert result.ok is True
    assert result.card_payload["total_steps"] == 0
    assert result.card_payload["steps"] == []


@pytest.mark.asyncio
async def test_compose_plan_creates_approve_step_for_erc20_swap(ctx):
    intent = {
        "title": "Swap USDC to ETH",
        "steps": [
            {
                "action": "swap",
                "params": {
                    "token_in": "USDC",
                    "token_out": "ETH",
                    "amount": "1000",
                    "chain_id": 1,
                },
            },
        ],
    }

    result = await compose_plan(ctx, intent=intent)

    assert result.ok is True
    steps = result.card_payload["steps"]
    # Should have approve + swap
    assert len(steps) == 2
    assert steps[0]["action"] == "approve"
    assert steps[1]["action"] == "swap"
    assert steps[1]["depends_on"] == [steps[0]["step_id"]]


@pytest.mark.asyncio
async def test_compose_plan_creates_wait_receipt_after_bridge(ctx):
    # Use native ETH for bridge to avoid extra approve step
    intent = {
        "title": "Bridge and swap",
        "steps": [
            {
                "action": "bridge",
                "params": {
                    "token": "ETH",
                    "amount": "1",
                    "src_chain_id": 1,
                    "dst_chain_id": 42161,
                },
            },
            {
                "action": "swap",
                "params": {
                    "token_in": "ETH",
                    "token_out": "USDC",
                    "amount": "1",
                    "chain_id": 42161,
                },
            },
        ],
    }

    result = await compose_plan(ctx, intent=intent)

    assert result.ok is True
    steps = result.card_payload["steps"]
    # bridge (native, no approve) + wait_receipt + swap (native, no approve) = 3
    assert len(steps) == 3
    assert steps[0]["action"] == "bridge"
    assert steps[1]["action"] == "wait_receipt"
    assert steps[1]["depends_on"] == [steps[0]["step_id"]]
    assert steps[2]["depends_on"] == [steps[1]["step_id"]]
