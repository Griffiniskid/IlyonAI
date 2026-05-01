"""Agent chat storage layer.

Provides CRUD operations for agent chat history.
Uses SQLAlchemy async with SQLite/PostgreSQL compatibility.
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text, update

from src.storage.database import Database, AgentChatRow, AgentChatMessageRow


# ── Lightweight data holders (no ORM dependency) ──────────────────────────

class ChatRow:
    """Minimal representation of an agent_chats row."""
    __slots__ = ("id", "user_id", "title", "created_at", "updated_at")

    def __init__(
        self,
        id: str,
        user_id: int,
        title: Optional[str],
        created_at: datetime,
        updated_at: datetime,
    ):
        self.id = id
        self.user_id = user_id
        self.title = title
        self.created_at = created_at
        self.updated_at = updated_at


class ChatMessageRow:
    """Minimal representation of an agent_chat_messages row."""
    __slots__ = ("id", "chat_id", "role", "content", "cards", "created_at")

    def __init__(
        self,
        id: int,
        chat_id: str,
        role: str,
        content: str,
        cards: Optional[Dict[str, Any]],
        created_at: datetime,
    ):
        self.id = id
        self.chat_id = chat_id
        self.role = role
        self.content = content
        self.cards = cards
        self.created_at = created_at


# ── JSON serialization helpers ────────────────────────────────────────────

def _serialize_cards(cards: Optional[Dict[str, Any]]) -> Optional[str]:
    """Serialize a cards dict to JSON string for storage."""
    if cards is None:
        return None
    return json.dumps(cards)


def _deserialize_cards(value: Optional[str]) -> Optional[Dict[str, Any]]:
    """Deserialize a JSON string back to a cards dict."""
    if value is None:
        return None
    return json.loads(value)


# ── CRUD helpers ──────────────────────────────────────────────────────────

async def create_chat(db: Database, user_id: int, title: Optional[str] = None) -> ChatRow:
    """Create a new chat and return it."""
    chat_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    async with db.async_session() as session:
        row = AgentChatRow(
            id=chat_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.commit()
        return ChatRow(
            id=chat_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )


async def list_chats(db: Database, user_id: int, limit: int = 50) -> List[ChatRow]:
    """Return all chats for *user_id*, newest first."""
    async with db.async_session() as session:
        result = await session.execute(
            select(AgentChatRow)
            .where(AgentChatRow.user_id == user_id)
            .order_by(AgentChatRow.updated_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            ChatRow(
                id=r.id,
                user_id=r.user_id,
                title=r.title,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]


async def append_message(
    db: Database,
    chat_id: str,
    role: str,
    content: str,
    cards: Optional[Dict[str, Any]] = None,
) -> ChatMessageRow:
    """Append a message to a chat and bump the chat's updated_at."""
    now = datetime.utcnow()
    cards_json = _serialize_cards(cards)
    
    async with db.async_session() as session:
        row = AgentChatMessageRow(
            chat_id=chat_id,
            role=role,
            content=content,
            cards_json=cards_json,
            created_at=now,
        )
        session.add(row)
        
        # Bump updated_at on the parent chat
        await session.execute(
            update(AgentChatRow)
            .where(AgentChatRow.id == chat_id)
            .values(updated_at=now)
        )
        
        await session.commit()
        await session.refresh(row)
        
        return ChatMessageRow(
            id=row.id,
            chat_id=row.chat_id,
            role=row.role,
            content=row.content,
            cards=_deserialize_cards(row.cards_json),
            created_at=row.created_at,
        )


async def list_messages(db: Database, chat_id: str) -> List[ChatMessageRow]:
    """Return all messages for a chat, oldest first."""
    async with db.async_session() as session:
        result = await session.execute(
            select(AgentChatMessageRow)
            .where(AgentChatMessageRow.chat_id == chat_id)
            .order_by(AgentChatMessageRow.created_at.asc())
        )
        rows = result.scalars().all()
        return [
            ChatMessageRow(
                id=r.id,
                chat_id=r.chat_id,
                role=r.role,
                content=r.content,
                cards=_deserialize_cards(r.cards_json),
                created_at=r.created_at,
            )
            for r in rows
        ]
