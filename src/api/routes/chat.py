"""
AI Chat API routes.

POST /api/v1/chat                       - Send a message, get a reply (+ tool calls)
GET  /api/v1/chat/session               - Create a new session and return session_id
GET  /api/v1/chat/session/{session_id}  - Get conversation history
DELETE /api/v1/chat/session/{session_id}- Clear a session
"""

import logging
import uuid
from typing import Optional

from aiohttp import web

from src.ai.chat.engine import ChatEngine

logger = logging.getLogger(__name__)

_engine: Optional[ChatEngine] = None


async def init_chat(app: web.Application):
    global _engine
    _engine = ChatEngine()
    logger.info("ChatEngine initialized")


async def cleanup_chat(app: web.Application):
    global _engine
    if _engine:
        await _engine.close()
    logger.info("ChatEngine closed")


async def send_message(request: web.Request) -> web.Response:
    """
    POST /api/v1/chat

    Body:
      {
        "message": "Is 0xabc... safe to use?",
        "session_id": "optional-existing-session-uuid"
      }

    Returns:
      {
        "session_id": "...",
        "reply": "...",
        "tool_calls_made": [...],
        "tokens_used": 123,
        "latency_ms": 456
      }
    """
    if _engine is None:
        return web.json_response({"error": "Chat engine not available"}, status=503)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = (body.get("message") or "").strip()
    if not message:
        return web.json_response({"error": "message is required"}, status=400)

    if len(message) > 4000:
        return web.json_response({"error": "Message too long (max 4000 chars)"}, status=400)

    session_id = (body.get("session_id") or "").strip() or _engine.new_session_id()

    try:
        result = await _engine.chat(session_id=session_id, user_message=message)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return web.json_response({"error": "Chat processing failed"}, status=500)

    return web.json_response(result)


async def new_session(request: web.Request) -> web.Response:
    """
    GET /api/v1/chat/session

    Create and return a fresh session ID. The session is created lazily
    on first message — this just pre-generates the ID.
    """
    if _engine is None:
        return web.json_response({"error": "Chat engine not available"}, status=503)

    session_id = _engine.new_session_id()
    return web.json_response({
        "session_id": session_id,
        "message": "Session ready. POST to /api/v1/chat with this session_id to begin.",
    })


async def get_session_history(request: web.Request) -> web.Response:
    """
    GET /api/v1/chat/session/{session_id}

    Return the conversation history for a session.
    """
    if _engine is None:
        return web.json_response({"error": "Chat engine not available"}, status=503)

    session_id = request.match_info.get("session_id", "").strip()
    if not session_id:
        return web.json_response({"error": "session_id required"}, status=400)

    history = await _engine.get_history(session_id)
    if history is None:
        return web.json_response(
            {"error": f"Session '{session_id}' not found or expired"},
            status=404,
        )

    return web.json_response(history)


async def clear_session(request: web.Request) -> web.Response:
    """
    DELETE /api/v1/chat/session/{session_id}

    Clear a session's conversation history.
    """
    if _engine is None:
        return web.json_response({"error": "Chat engine not available"}, status=503)

    session_id = request.match_info.get("session_id", "").strip()
    if not session_id:
        return web.json_response({"error": "session_id required"}, status=400)

    _engine.memory.delete(session_id)
    return web.json_response({"message": f"Session '{session_id}' cleared."})


def setup_chat_routes(app: web.Application):
    """Register chat routes and lifecycle hooks."""
    app.on_startup.append(init_chat)
    app.on_cleanup.append(cleanup_chat)

    app.router.add_post("/api/v1/chat", send_message)
    app.router.add_get("/api/v1/chat/session", new_session)
    app.router.add_get("/api/v1/chat/session/{session_id}", get_session_history)
    app.router.add_delete("/api/v1/chat/session/{session_id}", clear_session)

    logger.info("Chat routes registered")
