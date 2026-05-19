"""V7-020 spec-path package — LangChain chat model + OpenRouter client.

Two responsibilities collapse into this package:

1. ``IlyonChatModel`` — LangChain-compatible ``BaseChatModel`` wrapping
   the project's AI router. Migrated from the legacy ``src/agent/llm.py``
   single-file module when the package directory was introduced for
   V7-020 (Python resolves the package ahead of the file, so the file
   would have become unreachable otherwise).

2. ``OpenAIClient`` / ``OpenRouterClient`` — re-exported from
   ``src.ai.openai_client`` so spec-style imports such as
   ``from src.agent.llm.openrouter_client import OpenAIClient`` work
   without duplicating the dual-provider client. Both names refer to the
   same class; the alias exists so callers reading the code can see
   intent.
"""
from __future__ import annotations

from typing import Any, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from src.ai.openai_client import OpenAIClient


# Alias kept distinct so call sites can express intent ("I'm constructing
# an OpenRouter-backed client") even though the class is one and the same.
OpenRouterClient = OpenAIClient


class IlyonChatModel(BaseChatModel):
    """Wraps src/ai/router (or any duck-typed ``complete`` callable) as a
    LangChain ``BaseChatModel`` so it can be used with agents and memory."""

    router: Any = Field(...)
    model: str = "default"
    temperature: float = 0.2

    @property
    def _llm_type(self) -> str:
        return "ilyon-router"

    def _to_openai(self, messages: List[BaseMessage]) -> list[dict]:
        """Convert LangChain messages to OpenAI-style dicts."""
        role_map = {
            "human": "user",
            "system": "system",
            "ai": "assistant",
            "tool": "tool",
        }
        return [
            {"role": role_map.get(m.type, m.type), "content": m.content}
            for m in messages
        ]

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop=None,
        run_manager=None,
        **kw,
    ) -> ChatResult:
        resp = await self.router.complete(
            model=self.model,
            messages=self._to_openai(messages),
            temperature=kw.get("temperature", self.temperature),
            stop=stop,
            tools=kw.get("tools"),
            max_tokens=kw.get("max_tokens"),
        )
        msg = AIMessage(
            content=resp["content"],
            additional_kwargs={"tool_calls": resp.get("tool_calls", [])},
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _generate(
        self,
        messages: List[BaseMessage],
        stop=None,
        run_manager=None,
        **kw,
    ) -> ChatResult:
        import asyncio

        return asyncio.get_event_loop().run_until_complete(
            self._agenerate(messages, stop=stop, **kw)
        )


__all__ = [
    "IlyonChatModel",
    "OpenAIClient",
    "OpenRouterClient",
]
