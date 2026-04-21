"""ORM models for agent chat sessions and messages."""
import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from src.storage.database import Base


class Chat(Base):
    """A chat session owned by a web user."""

    __tablename__ = "chats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        BigInteger,
        ForeignKey("web_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(200), nullable=False, default="New Chat")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    """An individual message within a chat session."""

    __tablename__ = "chat_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chat_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    cards = Column(JSONB, nullable=True)
    tool_trace = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, default="complete")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


Index("ix_chat_messages_chat_id", ChatMessage.chat_id, ChatMessage.created_at)
