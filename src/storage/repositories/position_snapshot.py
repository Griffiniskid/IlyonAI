"""V7-022 async repo helpers for `position_snapshots`.

Mirrors the V7-023 `position_alert.py` pattern — raw `sa.text()` SQL
so the same code paths work on PostgreSQL (JSONB) and SQLite (TEXT
JSON). Payload always serialised here as a sorted JSON string for
on-disk shape stability across dialects.

Callers own the session. `insert_snapshot` returns the autoincrement
PK (`snapshot_id`, surfaced as `id` in the spec). `get_latest_snapshots`
returns rows ordered by `snapshot_at DESC` and respects `limit`.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text


_INSERT_SQL = text(
    """
    INSERT INTO position_snapshots (position_id, payload)
    VALUES (:position_id, :payload)
    """
)

_INSERT_RETURNING_SQL = text(
    """
    INSERT INTO position_snapshots (position_id, payload)
    VALUES (:position_id, :payload)
    RETURNING snapshot_id
    """
)

_SELECT_LATEST_SQL = text(
    """
    SELECT snapshot_id AS id,
           position_id,
           snapshot_at,
           payload
      FROM position_snapshots
     WHERE position_id = :position_id
     ORDER BY snapshot_at DESC, snapshot_id DESC
     LIMIT :limit
    """
)


def _serialize_payload(payload: dict | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True, default=str)


def _deserialize_payload(value: Any) -> dict | None:
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


async def insert_snapshot(
    session: Any,
    position_id: str,
    payload: dict,
) -> int:
    """Insert one snapshot row and return its autoincrement PK."""
    params = {
        "position_id": position_id,
        "payload": _serialize_payload(payload),
    }

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

    result = await session.execute(_INSERT_RETURNING_SQL, params)
    row = result.mappings().first()
    if row is None:
        return 0
    return int(row.get("snapshot_id") or row.get("id") or 0)


async def get_latest_snapshots(
    session: Any,
    position_id: str,
    limit: int = 1,
) -> list[dict]:
    """Return the most recent `limit` snapshots for `position_id`, newest first."""
    result = await session.execute(
        _SELECT_LATEST_SQL,
        {"position_id": position_id, "limit": int(limit)},
    )
    rows = result.mappings().all()
    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "id": int(row["id"]) if row.get("id") is not None else None,
                "position_id": row["position_id"],
                "snapshot_at": row.get("snapshot_at"),
                "payload": _deserialize_payload(row.get("payload")),
            }
        )
    return out
