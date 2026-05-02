"""Persistent windowed memory that rehydrates from the chat_messages table."""
from __future__ import annotations

from langchain.memory import ConversationBufferWindowMemory
from langchain_core.messages import AIMessage, HumanMessage

from src.storage.chat import last_messages


class PersistentWindowMemory(ConversationBufferWindowMemory):
    """ConversationBufferWindowMemory that loads history from the database."""

    @classmethod
    async def load(cls, db, chat_id: str, k: int = 10) -> "PersistentWindowMemory":
        """Build a memory instance pre-loaded with the last *k* messages."""
        mem = cls(k=k, return_messages=True, memory_key="chat_history")
        for m in await last_messages(db, chat_id, k):
            if m.role == "user":
                mem.chat_memory.add_user_message(m.content)
            else:
                mem.chat_memory.add_ai_message(m.content)
        return mem
