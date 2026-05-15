"""Persistence layer for §11 D.8 HMAC audit chain.

Writes AuditEntry rows into the session_key_audit_log table (agent_007
schema). Read API surfaces the chain for the Settings page audit-log
view.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Protocol

from src.defi.audit_trail import AuditEntry


class _SupportsExecute(Protocol):
    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any: ...


_INSERT_SQL = (
    "INSERT INTO session_key_audit_log "
    "(policy_id, user_wallet, action, prompt_hash, plan_hash, "
    " tx_hash, entry_hmac, prev_hmac, payload_json, timestamp) "
    "VALUES (:policy_id, :user_wallet, :action, :prompt_hash, "
    "        :plan_hash, :tx_hash, :entry_hmac, :prev_hmac, :payload_json, "
    "        :timestamp)"
)


def _entry_to_row(
    entry: AuditEntry,
    *,
    policy_id: str | None = None,
    user_wallet: str | None = None,
    action: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """AuditEntry is the minimal hash chain; persistence augments it with
    policy/user/action/payload context the caller carries alongside.
    """
    return {
        "policy_id": policy_id,
        "user_wallet": user_wallet.lower() if user_wallet else None,
        "action": action,
        "prompt_hash": entry.prompt_hash,
        "plan_hash": entry.plan_hash,
        "tx_hash": entry.tx_hash,
        "entry_hmac": entry.entry_hmac,
        "prev_hmac": entry.prev_hmac,
        "payload_json": json.dumps(payload) if payload else None,
        "timestamp": entry.timestamp,
    }


async def persist_entry(
    session: _SupportsExecute, entry: AuditEntry,
    *,
    policy_id: str | None = None,
    user_wallet: str | None = None,
    action: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    from sqlalchemy import text
    row = _entry_to_row(
        entry, policy_id=policy_id, user_wallet=user_wallet,
        action=action, payload=payload,
    )
    await session.execute(text(_INSERT_SQL), row)


async def persist_chain(
    session: _SupportsExecute,
    entries: Iterable[AuditEntry],
    *,
    policy_id: str | None = None,
    user_wallet: str | None = None,
    action: str | None = None,
) -> int:
    n = 0
    for e in entries:
        await persist_entry(
            session, e,
            policy_id=policy_id, user_wallet=user_wallet, action=action,
        )
        n += 1
    return n


async def read_chain_for_user(
    session: _SupportsExecute, *,
    user_wallet: str, limit: int = 200,
) -> list[dict[str, Any]]:
    from sqlalchemy import text
    sql = text(
        "SELECT * FROM session_key_audit_log "
        "WHERE user_wallet = :w "
        "ORDER BY created_at DESC LIMIT :limit"
    )
    result = await session.execute(sql, {"w": user_wallet.lower(), "limit": limit})
    rows = result.mappings().all() if hasattr(result, "mappings") else list(result)
    return [dict(r) for r in rows]


async def read_chain_for_policy(
    session: _SupportsExecute, *,
    policy_id: str, limit: int = 200,
) -> list[dict[str, Any]]:
    from sqlalchemy import text
    sql = text(
        "SELECT * FROM session_key_audit_log "
        "WHERE policy_id = :pid "
        "ORDER BY created_at DESC LIMIT :limit"
    )
    result = await session.execute(sql, {"pid": policy_id, "limit": limit})
    rows = result.mappings().all() if hasattr(result, "mappings") else list(result)
    return [dict(r) for r in rows]
