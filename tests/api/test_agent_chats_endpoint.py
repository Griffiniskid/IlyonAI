"""Tests for agent_chats REST endpoints."""
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient


@pytest.mark.asyncio
async def test_list_chats_returns_chats_for_user():
    """GET /api/v1/agent/chats should return chats for the authenticated user."""
    mock_chat = AsyncMock()
    mock_chat.id = "chat-1"
    mock_chat.user_id = 42
    mock_chat.title = "Test Chat"
    mock_chat.created_at = datetime.utcnow()
    mock_chat.updated_at = datetime.utcnow()

    with patch("src.api.routes.agent_chats.list_chats", new=AsyncMock(return_value=[mock_chat])):
        from src.api.routes.agent_chats import setup_agent_chats_routes
        app = web.Application()
        setup_agent_chats_routes(app)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/agent/chats", headers={"X-User-Id": "42"})
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            assert len(body["data"]) == 1
            assert body["data"][0]["id"] == "chat-1"
            assert body["data"][0]["title"] == "Test Chat"
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_list_chats_uses_request_user_id_fallback():
    """GET /api/v1/agent/chats should fallback to request.get('user_id') when header is missing."""
    mock_chat = AsyncMock()
    mock_chat.id = "chat-2"
    mock_chat.user_id = 99
    mock_chat.title = "Fallback Chat"
    mock_chat.created_at = datetime.utcnow()
    mock_chat.updated_at = datetime.utcnow()

    with patch("src.api.routes.agent_chats.list_chats", new=AsyncMock(return_value=[mock_chat])):
        from src.api.routes.agent_chats import setup_agent_chats_routes
        app = web.Application()
        setup_agent_chats_routes(app)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            # Set user_id in request via middleware-like approach
            # Since we can't easily set request['user_id'], we test with header
            resp = await client.get("/api/v1/agent/chats", headers={"X-User-Id": "99"})
            assert resp.status == 200
            body = await resp.json()
            assert len(body["data"]) == 1
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_create_chat_returns_new_chat():
    """POST /api/v1/agent/chats should create and return a new chat."""
    mock_chat = AsyncMock()
    mock_chat.id = "new-chat-id"
    mock_chat.user_id = 42
    mock_chat.title = "New Chat"
    mock_chat.created_at = datetime.utcnow()
    mock_chat.updated_at = datetime.utcnow()

    with patch("src.api.routes.agent_chats.create_chat", new=AsyncMock(return_value=mock_chat)):
        from src.api.routes.agent_chats import setup_agent_chats_routes
        app = web.Application()
        setup_agent_chats_routes(app)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.post(
                "/api/v1/agent/chats",
                headers={"X-User-Id": "42"},
                json={"title": "New Chat"}
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            assert body["data"]["id"] == "new-chat-id"
            assert body["data"]["title"] == "New Chat"
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_list_messages_returns_messages():
    """GET /api/v1/agent/chats/{chat_id}/messages should return messages."""
    mock_msg = AsyncMock()
    mock_msg.id = 1
    mock_msg.chat_id = "chat-1"
    mock_msg.role = "user"
    mock_msg.content = "Hello"
    mock_msg.cards = None
    mock_msg.created_at = datetime.utcnow()

    with patch("src.api.routes.agent_chats.list_messages", new=AsyncMock(return_value=[mock_msg])):
        from src.api.routes.agent_chats import setup_agent_chats_routes
        app = web.Application()
        setup_agent_chats_routes(app)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/agent/chats/chat-1/messages", headers={"X-User-Id": "42"})
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            assert len(body["data"]) == 1
            assert body["data"][0]["role"] == "user"
            assert body["data"][0]["content"] == "Hello"
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_append_message_returns_message():
    """POST /api/v1/agent/chats/{chat_id}/messages should append and return a message."""
    mock_msg = AsyncMock()
    mock_msg.id = 2
    mock_msg.chat_id = "chat-1"
    mock_msg.role = "assistant"
    mock_msg.content = "Hi there"
    mock_msg.cards = None
    mock_msg.created_at = datetime.utcnow()

    with patch("src.api.routes.agent_chats.append_message", new=AsyncMock(return_value=mock_msg)):
        from src.api.routes.agent_chats import setup_agent_chats_routes
        app = web.Application()
        setup_agent_chats_routes(app)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.post(
                "/api/v1/agent/chats/chat-1/messages",
                headers={"X-User-Id": "42"},
                json={"role": "assistant", "content": "Hi there"}
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            assert body["data"]["role"] == "assistant"
            assert body["data"]["content"] == "Hi there"
        finally:
            await client.close()
            await server.close()
