"""Tests for IlyonChatModel."""
import pytest

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.llm import IlyonChatModel


class FakeRouter:
    """Minimal stub that mimics the router.complete() interface."""

    async def complete(self, *, model, messages, temperature, stop, tools=None):
        return {
            "content": f"echo:{messages[-1]['content']}",
            "tool_calls": [],
        }


@pytest.mark.asyncio
async def test_generate_roundtrips_via_router():
    llm = IlyonChatModel(router=FakeRouter(), model="fake-model")
    out = await llm._agenerate(
        [SystemMessage(content="sys"), HumanMessage(content="hi")]
    )
    assert "echo:hi" in out.generations[0].message.content


@pytest.mark.asyncio
async def test_llm_type():
    llm = IlyonChatModel(router=FakeRouter())
    assert llm._llm_type == "ilyon-router"


@pytest.mark.asyncio
async def test_to_openai_mapping():
    llm = IlyonChatModel(router=FakeRouter())
    msgs = [
        SystemMessage(content="s"),
        HumanMessage(content="h"),
    ]
    result = llm._to_openai(msgs)
    assert result == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "h"},
    ]


@pytest.mark.asyncio
async def test_tool_calls_forwarded():
    class ToolRouter:
        async def complete(self, *, model, messages, temperature, stop, tools=None):
            return {
                "content": "",
                "tool_calls": [{"id": "c1", "function": "f", "args": {}}],
            }

    llm = IlyonChatModel(router=ToolRouter())
    out = await llm._agenerate([HumanMessage(content="go")])
    assert out.generations[0].message.additional_kwargs["tool_calls"] == [
        {"id": "c1", "function": "f", "args": {}}
    ]
