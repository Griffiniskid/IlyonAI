"""Chat persistence helpers for the agent platform.

Expects the chats / chat_messages tables created by migration agent_001.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession


# ── Lightweight data holders (no ORM dependency) ──────────────────────────

class ChatRow:
    """Minimal representation of a chats row."""
    __slots__ = ("id", "title", "created_at", "updated_at")

    def __init__(self, id: str, title: str, created_at: Optional[datetime], updated_at: Optional[datetime]):
        self.id = id
        self.title = title
        self.created_at = created_at
        self.updated_at = updated_at


class ChatMessageRow:
    __slots__ = ("id", "chat_id", "role", "content", "created_at")

    def __init__(self, id: str, chat_id: str, role: str, content: str, created_at: Optional[datetime]):
        self.id = id
        self.chat_id = chat_id
        self.role = role
        self.content = content
        self.created_at = created_at


# ── CRUD helpers ──────────────────────────────────────────────────────────

async def list_chats(session: AsyncSession, user_id: int) -> list[ChatRow]:
    """Return all chats for *user_id*, newest first."""
    result = await session.execute(
        text(
            "SELECT id, title, created_at, updated_at FROM chats "
            "WHERE user_id = :uid ORDER BY updated_at DESC NULLS LAST, created_at DESC"
        ),
        {"uid": user_id},
    )
    return [
        ChatRow(id=str(r[0]), title=r[1], created_at=r[2], updated_at=r[3])
        for r in result
    ]


async def get_chat(session: AsyncSession, chat_id: str, user_id: int) -> Optional[ChatRow]:
    """Fetch a single chat, scoped to *user_id*."""
    result = await session.execute(
        text(
            "SELECT id, title, created_at, updated_at FROM chats "
            "WHERE id = :cid AND user_id = :uid"
        ),
        {"cid": chat_id, "uid": user_id},
    )
    row = result.first()
    if row is None:
        return None
    return ChatRow(id=str(row[0]), title=row[1], created_at=row[2], updated_at=row[3])


async def get_chat_messages(session: AsyncSession, chat_id: str) -> list[ChatMessageRow]:
    """Return all messages for a chat, oldest first."""
    result = await session.execute(
        text(
            "SELECT id, chat_id, role, content, created_at FROM chat_messages "
            "WHERE chat_id = :cid ORDER BY created_at ASC"
        ),
        {"cid": chat_id},
    )
    return [
        ChatMessageRow(
            id=str(r[0]), chat_id=str(r[1]), role=r[2],
            content=r[3], created_at=r[4],
        )
        for r in result
    ]


async def delete_chat(session: AsyncSession, chat_id: str, user_id: int) -> bool:
    """Delete a chat (and its messages via FK cascade). Returns True if deleted."""
    result = await session.execute(
        text("DELETE FROM chats WHERE id = :cid AND user_id = :uid"),
        {"cid": chat_id, "uid": user_id},
    )
    return (result.rowcount or 0) > 0


async def create_chat(session: AsyncSession, user_id: int, title: str) -> ChatRow:
    """Create a new chat and return it."""
    chat_id = str(uuid.uuid4())
    now = datetime.utcnow()
    await session.execute(
        text("INSERT INTO chats (id, user_id, title, created_at, updated_at) VALUES (:id, :uid, :t, :c, :u)"),
        {"id": chat_id, "uid": user_id, "t": title, "c": now, "u": now},
    )
    return ChatRow(id=chat_id, title=title, created_at=now, updated_at=now)


async def append_message(
    session: AsyncSession,
    chat_id: str,
    role: str,
    content: str,
) -> ChatMessageRow:
    """Append a message to a chat and bump the chat's updated_at."""
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow()
    await session.execute(
        text(
            "INSERT INTO chat_messages (id, chat_id, role, content, created_at) "
            "VALUES (:id, :cid, :role, :content, :c)"
        ),
        {"id": msg_id, "cid": chat_id, "role": role, "content": content, "c": now},
    )
    # Bump updated_at on the parent chat
    await session.execute(
        text("UPDATE chats SET updated_at = :now WHERE id = :cid"),
        {"now": now, "cid": chat_id},
    )
    return ChatMessageRow(id=msg_id, chat_id=chat_id, role=role, content=content, created_at=now)


async def last_messages(session: AsyncSession, chat_id: str, k: int = 10) -> list[ChatMessageRow]:
    """Return the *k* most recent messages for a chat (oldest first).

    Used by PersistentWindowMemory to rehydrate conversation context.
    """
    result = await session.execute(
        text(
            "SELECT id, chat_id, role, content, created_at FROM chat_messages "
            "WHERE chat_id = :cid ORDER BY created_at DESC LIMIT :k"
        ),
        {"cid": chat_id, "k": k},
    )
    rows = [
        ChatMessageRow(
            id=str(r[0]), chat_id=str(r[1]), role=r[2],
            content=r[3], created_at=r[4],
        )
        for r in result
    ]
    return list(reversed(rows))
