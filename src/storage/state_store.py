"""V7-075 — Unified State Store keyed by intent_id.

Spec §1 invariant. Backed by the `intent_state` table (migration
agent_013, 2026-05-18). Provides the two helpers the state-machine
calls through:

  * upsert_intent_state(session, intent_id, status, current_step, payload)
        Idempotent INSERT-or-UPDATE. Mints the row on first sight and
        overwrites status / current_step / payload / updated_at on
        every subsequent call. The payload is JSON-serialised so the
        same shape persists across JSONB (PG) and JSON-as-TEXT (SQLite).

  * get_intent_state(session, intent_id) -> Optional[dict]
        Returns the latest persisted row as a dict, or None when the
        intent_id has never been written. The dict shape mirrors the
        column names so callers can `.get("status")` / `.get("payload")`
        directly.

No business logic lives here — this is the storage seam the
state-machine reads/writes through. The dispatcher decides what status
transitions are legal; we just persist the verdict.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import text


# Single-source SQL strings — kept as module constants so tests can
# assert exact wire shape and future refactors only touch one place.
_UPSERT_SQL_SQLITE = text(
    """
    INSERT INTO intent_state (intent_id, status, current_step, payload, updated_at)
    VALUES (:intent_id, :status, :current_step, :payload, CURRENT_TIMESTAMP)
    ON CONFLICT(intent_id) DO UPDATE SET
        status = excluded.status,
        current_step = excluded.current_step,
        payload = excluded.payload,
        updated_at = CURRENT_TIMESTAMP
    """
)

_UPSERT_SQL_PG = text(
    """
    INSERT INTO intent_state (intent_id, status, current_step, payload, updated_at)
    VALUES (:intent_id, :status, :current_step, CAST(:payload AS JSONB), CURRENT_TIMESTAMP)
    ON CONFLICT (intent_id) DO UPDATE SET
        status = EXCLUDED.status,
        current_step = EXCLUDED.current_step,
        payload = EXCLUDED.payload,
        updated_at = CURRENT_TIMESTAMP
    """
)

_SELECT_SQL = text(
    """
    SELECT intent_id, status, current_step, payload, updated_at
    FROM intent_state
    WHERE intent_id = :intent_id
    """
)


def _dialect_name(session: Any) -> str:
    """Best-effort dialect probe (matches V7-004 / agent_012 patterns)."""
    bind = getattr(session, "bind", None)
    dialect = getattr(bind, "dialect", None)
    return getattr(dialect, "name", "") or ""


async def upsert_intent_state(
    session: Any,
    intent_id: str,
    status: str,
    current_step: int,
    payload: dict,
) -> None:
    """Idempotent upsert of the canonical intent_state row.

    The same call mints the row on first sight and overwrites on
    every subsequent invocation. `updated_at` is server-stamped via
    CURRENT_TIMESTAMP so the wall clock is the DB's, not the app's.

    `payload` is always JSON-serialised before binding so the wire
    shape is identical between PostgreSQL (cast to JSONB) and SQLite
    (stored as JSON text). Callers pass a native Python dict.
    """
    if not intent_id:
        raise ValueError("intent_id is required")
    if not status:
        raise ValueError("status is required")
    if current_step is None or current_step < 0:
        raise ValueError("current_step must be a non-negative integer")
    payload_json = json.dumps(payload or {}, separators=(",", ":"), sort_keys=True)
    dialect = _dialect_name(session)
    stmt = _UPSERT_SQL_PG if dialect == "postgresql" else _UPSERT_SQL_SQLITE
    await session.execute(
        stmt,
        {
            "intent_id": intent_id,
            "status": status,
            "current_step": int(current_step),
            "payload": payload_json,
        },
    )


async def get_intent_state(session: Any, intent_id: str) -> Optional[dict]:
    """Fetch the canonical intent_state row by intent_id.

    Returns a plain dict on hit (keys: intent_id, status, current_step,
    payload, updated_at) with the JSON payload pre-parsed into a
    native dict. Returns None when the intent_id has never been
    persisted. The accessor never raises on miss — callers .get() the
    fields they need.
    """
    if not intent_id:
        return None
    result = await session.execute(_SELECT_SQL, {"intent_id": intent_id})
    row = result.mappings().first()
    if row is None:
        return None
    out = dict(row)
    # Normalise the payload back into a native dict regardless of
    # whether the dialect stored it as JSONB (already a dict) or JSON
    # text (string that needs json.loads).
    payload = out.get("payload")
    if isinstance(payload, str):
        try:
            out["payload"] = json.loads(payload)
        except (TypeError, ValueError):
            out["payload"] = {}
    elif payload is None:
        out["payload"] = {}
    return out
