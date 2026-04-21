"""
Agent v2 API routes.

Chat CRUD endpoints are wired; the agent-turn and post-message
endpoints remain stubs until the agent loop is implemented.
"""
from __future__ import annotations

from aiohttp import web

from src.config import settings

routes = web.RouteTableDef()


def _flag_off() -> web.Response:
    return web.json_response({"error": "agent_v2_disabled"}, status=503)


# ── Agent turn (SSE streaming) ─────────────────────────────────────────────

@routes.post("/api/v1/agent")
async def agent_turn(request: web.Request) -> web.StreamResponse:
    """Agent v2 main endpoint: accepts a user message, streams ReAct steps as SSE."""
    if not settings.FEATURE_AGENT_V2:
        return web.json_response({"error": "agent_v2_disabled"}, status=503)

    from src.api.middleware.rate_limit import agent_gap

    body = await request.json()
    session_id = body.get("session_id", "")
    wallet = request.get("user_wallet") or body.get("wallet")
    user_id = request.get("user_id", 0)

    if not agent_gap.allow(user_id, session_id):
        return web.json_response({"error": "rate_limited"}, status=429)

    from src.agent.clean import normalize_short_swap_query
    from src.agent.streaming import encode_sse
    from src.api.schemas.agent import DoneFrame, FinalFrame

    response = web.StreamResponse(
        status=200,
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
    )
    await response.prepare(request)

    try:
        message = normalize_short_swap_query(body.get("message", ""))

        # Skeleton: when db + router + tools are wired (post-W2), this will
        # delegate to run_turn(). For now we emit a placeholder response.
        f = FinalFrame(
            content="Agent v2 is initializing. Tools not yet registered.",
            card_ids=[],
            elapsed_ms=0,
            steps=0,
        )
        await response.write(encode_sse("final", f.model_dump()))
        d = DoneFrame()
        await response.write(encode_sse("done", d.model_dump()))
    except Exception as e:
        import json

        await response.write(
            f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n".encode()
        )

    await response.write_eof()
    return response


# ── Chat session CRUD ─────────────────────────────────────────────────────

@routes.get("/api/v1/agent/sessions")
async def list_sessions(request: web.Request) -> web.Response:
    """List all chat sessions for the authenticated user."""
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    wallet = request.get("user_wallet")
    if not wallet:
        return web.json_response({"error": "auth_required"}, status=401)

    try:
        from src.storage.database import get_database
        from src.storage.chat import list_chats
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        db = await get_database()
        # Resolve user_id from wallet_address
        async with db._engine.connect() as conn:
            r = await conn.execute(
                text("SELECT id FROM web_users WHERE wallet_address = :wa"),
                {"wa": wallet},
            )
            row = r.first()
            if not row:
                return web.json_response({"sessions": []})
            user_id = row[0]

        async with AsyncSession(db._engine) as session:
            chats = await list_chats(session, user_id)
            return web.json_response({
                "sessions": [
                    {
                        "id": str(c.id),
                        "title": c.title,
                        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                    }
                    for c in chats
                ],
            })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get("/api/v1/agent/sessions/{session_id}")
async def get_session(request: web.Request) -> web.Response:
    """Get a single chat session with its messages."""
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    wallet = request.get("user_wallet")
    if not wallet:
        return web.json_response({"error": "auth_required"}, status=401)

    session_id = request.match_info["session_id"]

    try:
        from src.storage.database import get_database
        from src.storage.chat import get_chat, get_chat_messages
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        db = await get_database()
        async with db._engine.connect() as conn:
            r = await conn.execute(
                text("SELECT id FROM web_users WHERE wallet_address = :wa"),
                {"wa": wallet},
            )
            row = r.first()
            if not row:
                return web.json_response({"error": "not_found"}, status=404)
            user_id = row[0]

        async with AsyncSession(db._engine) as session:
            chat = await get_chat(session, session_id, user_id)
            if chat is None:
                return web.json_response({"error": "not_found"}, status=404)
            messages = await get_chat_messages(session, session_id)
            return web.json_response({
                "id": str(chat.id),
                "title": chat.title,
                "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
                "messages": [
                    {
                        "id": str(m.id),
                        "role": m.role,
                        "content": m.content,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in messages
                ],
            })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.delete("/api/v1/agent/sessions/{session_id}")
async def delete_session(request: web.Request) -> web.Response:
    """Delete a chat session (and its messages via FK cascade)."""
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    wallet = request.get("user_wallet")
    if not wallet:
        return web.json_response({"error": "auth_required"}, status=401)

    session_id = request.match_info["session_id"]

    try:
        from src.storage.database import get_database
        from src.storage.chat import delete_chat
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        db = await get_database()
        async with db._engine.connect() as conn:
            r = await conn.execute(
                text("SELECT id FROM web_users WHERE wallet_address = :wa"),
                {"wa": wallet},
            )
            row = r.first()
            if not row:
                return web.json_response({"error": "not_found"}, status=404)
            user_id = row[0]

        async with AsyncSession(db._engine) as session:
            deleted = await delete_chat(session, session_id, user_id)
            if not deleted:
                return web.json_response({"error": "not_found"}, status=404)
            await session.commit()
            return web.json_response({"deleted": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post("/api/v1/agent/sessions/{session_id}/messages")
async def post_message(request: web.Request) -> web.Response:
    """Post a message to a chat session (stub until agent loop is wired)."""
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    return web.json_response({"error": "not_implemented"}, status=501)


def setup_agent_routes(app: web.Application) -> None:
    """Register agent v2 routes on *app*."""
    app.router.add_routes(routes)
