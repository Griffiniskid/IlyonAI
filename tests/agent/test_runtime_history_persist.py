"""Tests for run_simple_turn persistence wrapper."""
import pytest
import uuid

from src.storage.agent_chats import list_messages
from src.storage.database import get_database


class MockRouter:
    """Minimal mock router for tests that hit the LLM fallback path."""

    async def complete(self, **kwargs):
        return {"content": "Hello!"}


@pytest.mark.asyncio
async def test_simple_runtime_persists_user_and_assistant_messages():
    """Calling run_simple_turn for an authenticated user should append
    both the user message and the final assistant response to agent_chat_messages."""
    from src.agent.simple_runtime import run_simple_turn

    chat_id = f"chat-test-persist-{uuid.uuid4().hex[:8]}"
    user_id = 99

    async for _ in run_simple_turn(
        message="hi",
        session_id=chat_id,
        user_id=user_id,
        wallet="0xU",
        tools=[],
        router=MockRouter(),
    ):
        pass

    db = await get_database()
    messages = await list_messages(db, chat_id=chat_id)
    roles = [m.role for m in messages]
    assert "user" in roles, f"user message missing, got {roles}"
    assert "assistant" in roles, f"assistant message missing, got {roles}"
