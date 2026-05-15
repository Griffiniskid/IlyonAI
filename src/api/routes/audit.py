"""§11 D.8 audit-trail read route — GET /api/v1/audit/{wallet}.

Reads `session_key_audit_log` (alembic agent_007) for the user's HMAC-
chained autonomous-action history. Frontend AuditLogPanel consumes the
returned entries.
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from src.defi.audit_persistence import read_chain_for_user

logger = logging.getLogger(__name__)


def _row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise a DB row to the AuditChainEntry shape the frontend expects."""
    created = row.get("created_at")
    ts_unix: float = 0.0
    try:
        if hasattr(created, "timestamp"):
            ts_unix = float(created.timestamp())
        elif isinstance(created, (int, float)):
            ts_unix = float(created)
    except Exception:  # noqa: BLE001
        ts_unix = 0.0
    return {
        "entry_id": str(row.get("entry_id") or row.get("id") or ""),
        "user_wallet": str(row.get("user_wallet") or ""),
        "prompt_hash": str(row.get("prompt_hash") or ""),
        "plan_hash": str(row.get("plan_hash") or ""),
        "tx_hash": row.get("tx_hash") or None,
        "prev_hmac": str(row.get("prev_hmac") or ""),
        "hmac": str(row.get("hmac") or ""),
        "ts": ts_unix,
    }


async def list_audit_entries(request: web.Request) -> web.Response:
    wallet = request.match_info["wallet"].lower()
    if not (wallet.startswith("0x") and len(wallet) == 42) and len(wallet) < 32:
        return web.json_response(
            {"ok": False, "error": "invalid_wallet"}, status=400,
        )
    try:
        limit = int(request.query.get("limit", "100"))
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 500))

    session_factory = request.app.get("_db_session_factory")
    if session_factory is None:
        cache = request.app.get("_audit_chain_cache", {}) or {}
        rows = list(cache.get(wallet, []))[:limit]
        return web.json_response(
            {"ok": True, "wallet": wallet, "entries": rows, "persisted": False}
        )
    try:
        async with session_factory() as session:
            rows = await read_chain_for_user(
                session, user_wallet=wallet, limit=limit,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit read failed: %s", exc)
        return web.json_response(
            {"ok": False, "error": "read_failed", "detail": str(exc)[:200]},
            status=500,
        )

    return web.json_response(
        {
            "ok": True,
            "wallet": wallet,
            "entries": [_row_to_payload(r) for r in rows],
            "persisted": True,
        }
    )


def setup_audit_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/audit/{wallet}", list_audit_entries)
