"""LangChain-compatible chat model wrapping the project's AI router."""
from __future__ import annotations

from typing import Any, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class IlyonChatModel(BaseChatModel):
    """Wraps src/ai/router (or any duck-typed ``complete`` callable) as a
    LangChain ``BaseChatModel`` so it can be used with agents and memory."""

    router: Any = Field(...)
    model: str = "default"
    temperature: float = 0.2

    @property
    def _llm_type(self) -> str:  # noqa: D401
        return "ilyon-router"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Sync / async generation
    # ------------------------------------------------------------------

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
            temperature=self.temperature,
            stop=stop,
            tools=kw.get("tools"),
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
