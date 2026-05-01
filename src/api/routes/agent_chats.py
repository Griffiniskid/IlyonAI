"""Agent chats REST API routes."""
from __future__ import annotations

from aiohttp import web

from src.storage.database import get_database
from src.storage.agent_chats import create_chat, list_chats, append_message, list_messages

routes = web.RouteTableDef()


def _get_user_id(request: web.Request) -> int:
    """Extract user_id from X-User-Id header or request storage."""
    header = request.headers.get("X-User-Id")
    if header:
        try:
            return int(header)
        except ValueError:
            pass
    return request.get("user_id", 0)


@routes.get("/api/v1/agent/chats")
async def get_chats(request: web.Request) -> web.Response:
    """List all chats for the authenticated user."""
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "auth_required"}, status=401)

    try:
        db = await get_database()
        chats = await list_chats(db, user_id=user_id)
        return web.json_response({
            "status": "ok",
            "data": [
                {
                    "id": c.id,
                    "user_id": c.user_id,
                    "title": c.title,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                }
                for c in chats
            ],
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post("/api/v1/agent/chats")
async def post_chat(request: web.Request) -> web.Response:
    """Create a new chat for the authenticated user."""
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "auth_required"}, status=401)

    try:
        body = await request.json()
        title = body.get("title") if isinstance(body, dict) else None
    except Exception:
        title = None

    try:
        db = await get_database()
        chat = await create_chat(db, user_id=user_id, title=title)
        return web.json_response({
            "status": "ok",
            "data": {
                "id": chat.id,
                "user_id": chat.user_id,
                "title": chat.title,
                "created_at": chat.created_at.isoformat() if chat.created_at else None,
                "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
            },
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get("/api/v1/agent/chats/{chat_id}/messages")
async def get_messages(request: web.Request) -> web.Response:
    """List all messages for a chat."""
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "auth_required"}, status=401)

    chat_id = request.match_info["chat_id"]

    try:
        db = await get_database()
        messages = await list_messages(db, chat_id=chat_id)
        return web.json_response({
            "status": "ok",
            "data": [
                {
                    "id": m.id,
                    "chat_id": m.chat_id,
                    "role": m.role,
                    "content": m.content,
                    "cards": m.cards,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post("/api/v1/agent/chats/{chat_id}/messages")
async def post_message(request: web.Request) -> web.Response:
    """Append a message to a chat."""
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "auth_required"}, status=401)

    chat_id = request.match_info["chat_id"]

    try:
        body = await request.json()
        if not isinstance(body, dict):
            return web.json_response({"error": "invalid_body"}, status=400)
        role = body.get("role", "user")
        content = body.get("content", "")
        cards = body.get("cards")
    except Exception:
        return web.json_response({"error": "invalid_body"}, status=400)

    try:
        db = await get_database()
        msg = await append_message(db, chat_id=chat_id, role=role, content=content, cards=cards)
        return web.json_response({
            "status": "ok",
            "data": {
                "id": msg.id,
                "chat_id": msg.chat_id,
                "role": msg.role,
                "content": msg.content,
                "cards": msg.cards,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            },
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def setup_agent_chats_routes(app: web.Application) -> None:
    """Register agent chats routes on *app*."""
    app.router.add_routes(routes)
