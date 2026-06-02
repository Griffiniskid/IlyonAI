from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    wallet_address: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    chats: Mapped[List[Chat]] = relationship("Chat", back_populates="user", cascade="all, delete-orphan")


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="New Chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped[User] = relationship("User", back_populates="chats")
    messages: Mapped[List[ChatMessage]] = relationship(
        "ChatMessage", back_populates="chat", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(36), ForeignKey("chats.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    chat: Mapped[Chat] = relationship("Chat", back_populates="messages")


class Transaction(Base):
    """A swap / bridge / transfer / stake / LP the user executed THROUGH this
    app. Logged client-side right after the wallet signs (the web has the
    signature/hash by then), keyed by wallet so the Activity view can list a
    user's interactions with the protocol. Wallets may be anonymous, so there
    is no FK to users — `wallet` is the lookup key."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    wallet: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # swap|bridge|transfer|stake|lp
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent|confirmed|failed
    chain: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    dst_chain: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # bridge only
    from_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    to_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    from_amount: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    to_amount: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    signature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)  # tx hash / sig
    order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # deBridge order
    explorer_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "wallet": self.wallet,
            "kind": self.kind,
            "status": self.status,
            "chain": self.chain,
            "dst_chain": self.dst_chain,
            "from_token": self.from_token,
            "to_token": self.to_token,
            "from_amount": self.from_amount,
            "to_amount": self.to_amount,
            "signature": self.signature,
            "order_id": self.order_id,
            "explorer_url": self.explorer_url,
            "created_at": (self.created_at.isoformat() if self.created_at else None),
        }
