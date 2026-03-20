"""Audit logging helpers for alert rule mutations."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any


logger = logging.getLogger(__name__)


_audit_records: list[dict[str, Any]] = []


async def write_audit_record(
    event_type: str,
    *,
    actor_id: str,
    trace_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an audit record in memory for security events."""
    record = {
        "event_type": event_type,
        "actor_id": actor_id,
        "trace_id": trace_id,
        "payload": payload or {},
        "created_at": datetime.utcnow().isoformat(),
    }
    _audit_records.append(record)

    try:
        from src.storage.database import get_database

        db = await get_database()
        await db.write_alert_audit_record(event_type, actor_id, trace_id, payload or {})
    except Exception as exc:
        logger.warning("Failed to persist alert audit record: %s", exc)

    return record


async def fetch_latest_audit_record(event_type: str) -> dict[str, Any] | None:
    """Return the latest matching audit record if present."""
    for record in reversed(_audit_records):
        if record["event_type"] == event_type:
            return record

    try:
        from src.storage.database import get_database

        db = await get_database()
        return await db.fetch_latest_alert_audit_record(event_type)
    except Exception as exc:
        logger.warning("Failed to fetch persisted alert audit record: %s", exc)
        return None


def clear_audit_log() -> None:
    """Clear in-memory audit records (tests)."""
    _audit_records.clear()
