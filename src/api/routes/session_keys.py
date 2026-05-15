"""Session-key management routes — §11 D.5/D.6 surface.

POST /api/v1/sessions/{policy_id}/revoke → one-click revoke.
GET  /api/v1/sessions/{user_wallet} → list active + revoked policies.

Backed by the `session_key_policies` table (alembic agent_007). Revoke
flips revoked_at = NOW(); the off-chain enforcement layer reads this
column before authorising any autonomous action and refuses revoked
policies. On-chain enforcement (Biconomy/ZeroDev policy framework) is
the Phase 7 follow-up; this route is the off-chain index that the
Settings page consumes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiohttp import web

logger = logging.getLogger(__name__)


async def revoke_session_key(request: web.Request) -> web.Response:
    policy_id = request.match_info["policy_id"]
    if not policy_id or len(policy_id) > 64:
        return web.json_response({"ok": False, "error": "invalid_policy_id"}, status=400)
    session_factory = request.app.get("_db_session_factory")
    if session_factory is None:
        # Soft-success when the DB isn't wired in this deployment — surface
        # the cached revocation in app state so frontends still observe the
        # flip in dev environments.
        cache = request.app.setdefault("_revoked_session_keys", {})
        cache[policy_id] = datetime.now(timezone.utc).isoformat()
        return web.json_response({"ok": True, "policy_id": policy_id, "revoked_at": cache[policy_id], "persisted": False})
    from sqlalchemy import text
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE session_key_policies SET revoked_at = :ts "
                "WHERE policy_id = :pid AND revoked_at IS NULL"
            ),
            {"ts": datetime.now(timezone.utc), "pid": policy_id},
        )
        await session.commit()
    logger.info("session-key revoke: policy_id=%s", policy_id)
    return web.json_response({"ok": True, "policy_id": policy_id, "persisted": True})


async def list_session_keys(request: web.Request) -> web.Response:
    user_wallet = request.match_info["user_wallet"].lower()
    session_factory = request.app.get("_db_session_factory")
    if session_factory is None:
        cache = request.app.get("_revoked_session_keys", {})
        return web.json_response({
            "ok": True, "user_wallet": user_wallet,
            "policies": [], "revoked_cache": cache,
            "persisted": False,
        })
    from sqlalchemy import text
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT policy_id, scope, spend_cap_24h_usd, expires_at, revoked_at "
                "FROM session_key_policies WHERE user_wallet = :w "
                "ORDER BY revoked_at NULLS FIRST, expires_at DESC LIMIT 100"
            ),
            {"w": user_wallet},
        )
        rows = result.mappings().all() if hasattr(result, "mappings") else list(result)
    return web.json_response({
        "ok": True,
        "user_wallet": user_wallet,
        "policies": [dict(r) for r in rows],
        "persisted": True,
    })


def setup_session_key_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/sessions/{policy_id}/revoke", revoke_session_key)
    app.router.add_get("/api/v1/sessions/{user_wallet}", list_session_keys)
