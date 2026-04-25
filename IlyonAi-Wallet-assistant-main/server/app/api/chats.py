from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import exists

from app.db.database import get_db
from app.db.models import Chat, ChatMessage, User
from app.api.auth import get_current_user

router = APIRouter(prefix="/chats", tags=["chats"])


class ChatOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatDetailOut(ChatOut):
    messages: List[MessageOut]


class CreateChatRequest(BaseModel):
    title: Optional[str] = "New Chat"


class RenameChatRequest(BaseModel):
    title: str


@router.get("", response_model=List[ChatOut])
def list_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Only return chats that have at least one message (filters out orphan empty chats)
    has_messages = exists().where(ChatMessage.chat_id == Chat.id)
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == current_user.id, has_messages)
        .order_by(Chat.updated_at.desc())
        .all()
    )
    return [ChatOut.model_validate(c) for c in chats]


@router.post("", response_model=ChatOut)
def create_chat(body: CreateChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = Chat(id=str(uuid.uuid4()), user_id=current_user.id, title=body.title or "New Chat")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return ChatOut.model_validate(chat)


@router.get("/{chat_id}", response_model=ChatDetailOut)
def get_chat(chat_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return ChatDetailOut(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=[MessageOut.model_validate(m) for m in chat.messages],
    )


@router.patch("/{chat_id}", response_model=ChatOut)
def rename_chat(chat_id: str, body: RenameChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat.title = body.title
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(chat)
    return ChatOut.model_validate(chat)


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    db.delete(chat)
    db.commit()
    return {"ok": True}
