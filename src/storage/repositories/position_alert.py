"""Async repository helpers for `position_alerts` (V7-023).

Raw `sa.text()` SQL is used (instead of the ORM model) so the repo
works identically on PostgreSQL (JSONB `payload`) and SQLite (TEXT
JSON `payload`) — the tests run on the latter, production runs on the
former. The JSON value is serialised here via `json.dumps()` so the
on-disk shape is stable across dialects.

Conventions:
  - Callers own the session (`async with db.async_session() as s: ...`)
    so multiple repo calls can compose into one transaction.
  - `insert_alert` returns the autoincrement PK (`alert_id`, surfaced
    as `id` in the spec).
  - `get_open_alerts` returns the rows where the V7-023 spec
    `dismissed_at` column is NULL — *not* the legacy
    `acknowledged_at` column from agent_006, because those are
    populated by older Notifier code that V7-023 explicitly
    supersedes.
  - `dismiss_alert` writes `CURRENT_TIMESTAMP` server-side so the wall
    clock is the DB's, not the app server's (matters when multiple
    workers race the same dismiss).
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text


_INSERT_SQL = text(
    """
    INSERT INTO position_alerts (position_id, alert_type, payload)
    VALUES (:position_id, :alert_type, :payload)
    """
)

_INSERT_RETURNING_SQL = text(
    """
    INSERT INTO position_alerts (position_id, alert_type, payload)
    VALUES (:position_id, :alert_type, :payload)
    RETURNING alert_id
    """
)

_SELECT_OPEN_SQL = text(
    """
    SELECT alert_id AS id,
           position_id,
           alert_type,
           fired_at,
           payload,
           dismissed_at
      FROM position_alerts
     WHERE position_id = :position_id
       AND dismissed_at IS NULL
     ORDER BY fired_at ASC
    """
)

_DISMISS_SQL = text(
    """
    UPDATE position_alerts
       SET dismissed_at = CURRENT_TIMESTAMP
     WHERE alert_id = :alert_id
    """
)


def _serialize_payload(payload: dict | None) -> str | None:
    """Always store payload as a JSON string.

    PostgreSQL's JSONB cast (`::jsonb`) accepts the same string shape,
    and SQLite's JSON type is just TEXT under the hood — so a single
    serialiser works for both. Returns None for null payloads.
    """
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True, default=str)


def _deserialize_payload(value: Any) -> dict | None:
    """Decode whatever the DB driver hands back to us.

    asyncpg returns Python dicts directly for JSONB; aiosqlite returns
    the stored TEXT. Either is acceptable — we normalise to `dict | None`.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return None


async def insert_alert(
    session: Any,
    position_id: str,
    alert_type: str,
    payload: dict,
) -> int:
    """Insert a new alert row and return its autoincrement PK.

    Uses `RETURNING alert_id` on PostgreSQL; falls back to a follow-up
    `last_insert_rowid()` on SQLite so the same call signature works
    in unit tests. The PK is surfaced as `id` in the spec / model /
    JSON contract — only the physical column stays `alert_id`.
    """
    params = {
        "position_id": position_id,
        "alert_type": alert_type,
        "payload": _serialize_payload(payload),
    }

    # Probe the dialect via the bound engine. asyncpg / asyncpg-style
    # adapters all expose `.bind.dialect.name`. We default to the
    # RETURNING path because PG is production; SQLite falls back.
    dialect_name = ""
    bind = getattr(session, "bind", None)
    if bind is not None:
        dialect = getattr(bind, "dialect", None)
        if dialect is not None:
            dialect_name = getattr(dialect, "name", "") or ""

    if dialect_name == "sqlite":
        await session.execute(_INSERT_SQL, params)
        result = await session.execute(text("SELECT last_insert_rowid() AS id"))
        row = result.mappings().first()
        return int(row["id"]) if row else 0

    # Default: PostgreSQL (or anything that supports RETURNING).
    result = await session.execute(_INSERT_RETURNING_SQL, params)
    row = result.mappings().first()
    if row is None:
        return 0
    # Column may come back as "alert_id" (no alias support) or as
    # "id" depending on driver quirks; accept either.
    return int(row.get("alert_id") or row.get("id") or 0)


async def get_open_alerts(
    session: Any,
    position_id: str,
) -> list[dict]:
    """Return all alerts for *position_id* where `dismissed_at IS NULL`.

    Rows are ordered by `fired_at ASC` so the oldest unhandled alert
    surfaces first — the frontend renders the alert chain in fire
    order under the position card.
    """
    result = await session.execute(
        _SELECT_OPEN_SQL,
        {"position_id": position_id},
    )
    rows = result.mappings().all()
    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "id": int(row["id"]) if row.get("id") is not None else None,
                "position_id": row["position_id"],
                "alert_type": row.get("alert_type"),
                "fired_at": row.get("fired_at"),
                "payload": _deserialize_payload(row.get("payload")),
                "dismissed_at": row.get("dismissed_at"),
            }
        )
    return out


async def dismiss_alert(session: Any, alert_id: int) -> None:
    """Mark *alert_id* as dismissed at the DB's wall clock.

    Idempotent: re-dismissing an already-dismissed alert overwrites
    `dismissed_at` with the newer timestamp. That's the desired
    behaviour for "user clicked dismiss twice" — we want the most
    recent acknowledgement.
    """
    await session.execute(_DISMISS_SQL, {"alert_id": int(alert_id)})
