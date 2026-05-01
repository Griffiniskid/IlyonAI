"""Tests for agent_chats storage layer."""
import pytest
from datetime import datetime
from src.storage.agent_chats import create_chat, list_chats, append_message, list_messages
from src.storage.database import get_database


@pytest.mark.asyncio
async def test_create_chat_returns_chat_with_id():
    """create_chat must return a chat row with id, user_id, title, and timestamps."""
    db = await get_database()
    chat = await create_chat(db, user_id=42, title="Test Chat")
    
    assert chat.id is not None
    assert chat.user_id == 42
    assert chat.title == "Test Chat"
    assert chat.created_at is not None
    assert chat.updated_at is not None


@pytest.mark.asyncio
async def test_list_chats_returns_user_chats():
    """list_chats must return chats for a specific user, newest first."""
    db = await get_database()
    user_id = 999990
    
    chat1 = await create_chat(db, user_id=user_id, title="Chat 1")
    chat2 = await create_chat(db, user_id=user_id, title="Chat 2")
    
    chats = await list_chats(db, user_id=user_id)
    
    assert len(chats) >= 2
    titles = [c.title for c in chats if c.user_id == user_id]
    assert "Chat 1" in titles
    assert "Chat 2" in titles
    # Newest first
    chat_ids = [c.id for c in chats if c.user_id == user_id]
    assert chat_ids[0] == chat2.id


@pytest.mark.asyncio
async def test_list_chats_respects_limit():
    """list_chats must respect the limit parameter."""
    db = await get_database()
    user_id = 999989
    
    await create_chat(db, user_id=user_id, title="Chat A")
    await create_chat(db, user_id=user_id, title="Chat B")
    await create_chat(db, user_id=user_id, title="Chat C")
    
    chats = await list_chats(db, user_id=user_id, limit=2)
    assert len(chats) == 2


@pytest.mark.asyncio
async def test_list_chats_does_not_return_other_users_chats():
    """list_chats must not return chats belonging to other users."""
    db = await get_database()
    user_a = 999988
    user_b = 999987
    
    await create_chat(db, user_id=user_a, title="User A Chat")
    await create_chat(db, user_id=user_b, title="User B Chat")
    
    chats = await list_chats(db, user_id=user_a)
    titles = [c.title for c in chats]
    assert "User A Chat" in titles
    assert "User B Chat" not in titles


@pytest.mark.asyncio
async def test_append_message_returns_message():
    """append_message must return a message row with id, role, content, and timestamp."""
    db = await get_database()
    chat = await create_chat(db, user_id=41, title="Message Test")
    
    msg = await append_message(db, chat_id=chat.id, role="user", content="Hello")
    
    assert msg.id is not None
    assert msg.chat_id == chat.id
    assert msg.role == "user"
    assert msg.content == "Hello"
    assert msg.created_at is not None
    assert msg.cards is None


@pytest.mark.asyncio
async def test_append_message_with_cards():
    """append_message must serialize cards dict to JSON and deserialize back."""
    db = await get_database()
    chat = await create_chat(db, user_id=40, title="Cards Test")
    
    cards = {"type": "analysis", "data": {"score": 85}}
    msg = await append_message(db, chat_id=chat.id, role="assistant", content="Result", cards=cards)
    
    assert msg.cards == cards


@pytest.mark.asyncio
async def test_list_messages_returns_ordered_messages():
    """list_messages must return messages for a chat, oldest first."""
    db = await get_database()
    chat = await create_chat(db, user_id=39, title="List Messages Test")
    
    msg1 = await append_message(db, chat_id=chat.id, role="user", content="First")
    msg2 = await append_message(db, chat_id=chat.id, role="assistant", content="Second")
    
    messages = await list_messages(db, chat_id=chat.id)
    
    assert len(messages) == 2
    assert messages[0].content == "First"
    assert messages[1].content == "Second"
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_list_messages_only_returns_chat_messages():
    """list_messages must only return messages for the specified chat."""
    db = await get_database()
    chat1 = await create_chat(db, user_id=38, title="Chat 1")
    chat2 = await create_chat(db, user_id=38, title="Chat 2")
    
    await append_message(db, chat_id=chat1.id, role="user", content="Chat 1 msg")
    await append_message(db, chat_id=chat2.id, role="user", content="Chat 2 msg")
    
    messages = await list_messages(db, chat_id=chat1.id)
    assert len(messages) == 1
    assert messages[0].content == "Chat 1 msg"


@pytest.mark.asyncio
async def test_chat_updated_at_changes_on_append():
    """Appending a message should update the chat's updated_at timestamp."""
    db = await get_database()
    chat = await create_chat(db, user_id=37, title="Update Test")
    original_updated_at = chat.updated_at
    
    # Small sleep to ensure time difference
    import asyncio
    await asyncio.sleep(0.01)
    
    await append_message(db, chat_id=chat.id, role="user", content="Update")
    
    chats = await list_chats(db, user_id=37)
    updated_chat = [c for c in chats if c.id == chat.id][0]
    assert updated_chat.updated_at > original_updated_at
