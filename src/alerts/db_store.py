"""Database-backed alert store — replaces InMemoryAlertStore for production."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select, delete

from src.alerts.models import AlertRecord, AlertRule
from src.alerts.orchestrator import advance_alert_state
from src.storage.database import get_database, AlertRuleRow, AlertRecordRow

logger = logging.getLogger(__name__)


class DatabaseAlertStore:
    def __init__(self):
        self._rule_counter = 0

    @staticmethod
    def _normalize_severity(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []

    async def _db(self):
        return await get_database()

    async def create_rule(self, payload: dict) -> AlertRule:
        db = await self._db()
        self._rule_counter += 1
        rule_id = f"r-{self._rule_counter}"
        name = str(payload.get("name", "unnamed"))
        severity = self._normalize_severity(payload.get("severity", []))

        async with db.async_session() as session:
            session.add(AlertRuleRow(id=rule_id, name=name, severity=severity))
            await session.commit()

        return AlertRule(id=rule_id, name=name, severity=severity)

    async def list_rules(self) -> list[AlertRule]:
        db = await self._db()
        async with db.async_session() as session:
            result = await session.execute(select(AlertRuleRow).order_by(AlertRuleRow.created_at))
            rows = result.scalars().all()
            rules = [AlertRule(id=r.id, name=r.name, severity=r.severity or []) for r in rows]
            # Keep counter in sync
            if rows:
                max_id = max(int(r.id.split("-")[1]) for r in rows if r.id.startswith("r-"))
                self._rule_counter = max(self._rule_counter, max_id)
            return rules

    async def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        db = await self._db()
        async with db.async_session() as session:
            result = await session.execute(select(AlertRuleRow).where(AlertRuleRow.id == rule_id))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return AlertRule(id=row.id, name=row.name, severity=row.severity or [])

    async def update_rule(self, rule_id: str, payload: dict) -> Optional[AlertRule]:
        db = await self._db()
        async with db.async_session() as session:
            result = await session.execute(select(AlertRuleRow).where(AlertRuleRow.id == rule_id))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            new_name = payload.get("name", row.name)
            new_severity = self._normalize_severity(payload["severity"]) if "severity" in payload else (row.severity or [])
            if "name" in payload:
                row.name = new_name
            if "severity" in payload:
                row.severity = new_severity
            await session.commit()
            # Use captured values instead of potentially stale ORM state
            return AlertRule(id=rule_id, name=new_name, severity=new_severity)

    async def delete_rule(self, rule_id: str) -> bool:
        db = await self._db()
        async with db.async_session() as session:
            result = await session.execute(delete(AlertRuleRow).where(AlertRuleRow.id == rule_id))
            await session.commit()
            return (result.rowcount or 0) > 0

    async def add_alert(self, alert: AlertRecord) -> AlertRecord:
        db = await self._db()
        async with db.async_session() as session:
            session.add(AlertRecordRow(
                id=alert.id, state=alert.state, severity=alert.severity,
                title=alert.title, user_id=alert.user_id, rule_id=alert.rule_id,
                subject_id=alert.subject_id, kind=alert.kind,
                snoozed_until=alert.snoozed_until, resolved_at=alert.resolved_at,
            ))
            await session.commit()

        # Publish to stream for real-time notifications
        try:
            from src.platform.stream_hub import get_stream_hub
            hub = get_stream_hub()
            await hub.publish("alerts", {
                "type": "alert_created",
                "alert": alert.model_dump(),
            })
        except Exception as e:
            logger.warning(f"Failed to publish alert event: {e}")

        return alert

    async def list_alerts(self, severity: str | None = None) -> list[AlertRecord]:
        db = await self._db()
        async with db.async_session() as session:
            stmt = select(AlertRecordRow).order_by(AlertRecordRow.created_at.desc())
            if severity:
                stmt = stmt.where(AlertRecordRow.severity == severity)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                AlertRecord(
                    id=r.id, state=r.state, severity=r.severity, title=r.title,
                    user_id=r.user_id, rule_id=r.rule_id, subject_id=r.subject_id,
                    kind=r.kind, snoozed_until=r.snoozed_until, resolved_at=r.resolved_at,
                    created_at=r.created_at.isoformat() if r.created_at else None,
                )
                for r in rows
            ]

    async def get_alert(self, alert_id: str) -> Optional[AlertRecord]:
        db = await self._db()
        async with db.async_session() as session:
            result = await session.execute(select(AlertRecordRow).where(AlertRecordRow.id == alert_id))
            r = result.scalar_one_or_none()
            if r is None:
                return None
            return AlertRecord(
                id=r.id, state=r.state, severity=r.severity, title=r.title,
                user_id=r.user_id, rule_id=r.rule_id, subject_id=r.subject_id,
                kind=r.kind, snoozed_until=r.snoozed_until, resolved_at=r.resolved_at,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )

    async def apply_alert_action(self, alert_id: str, action: str, snoozed_until: str | None = None) -> Optional[AlertRecord]:
        db = await self._db()
        async with db.async_session() as session:
            result = await session.execute(select(AlertRecordRow).where(AlertRecordRow.id == alert_id))
            row = result.scalar_one_or_none()
            if row is None:
                return None

            # Build a pydantic model to use the orchestrator
            alert = AlertRecord(
                id=row.id, state=row.state, severity=row.severity, title=row.title,
                user_id=row.user_id, rule_id=row.rule_id, subject_id=row.subject_id,
                kind=row.kind, snoozed_until=row.snoozed_until, resolved_at=row.resolved_at,
            )

            if action == "seen":
                if alert.state == "new":
                    advance_alert_state(alert, "seen")
            elif action == "acknowledge":
                if alert.state == "new":
                    advance_alert_state(alert, "seen")
                if alert.state == "seen":
                    advance_alert_state(alert, "acknowledged")
            elif action == "snooze":
                alert.snoozed_until = snoozed_until
            elif action == "resolve":
                if alert.state == "new":
                    advance_alert_state(alert, "seen")
                if alert.state == "seen":
                    advance_alert_state(alert, "acknowledged")
                alert.resolved_at = datetime.now(UTC).isoformat()
            elif action == "unsnooze":
                alert.snoozed_until = None
            else:
                raise ValueError(f"unsupported action: {action}")

            # Persist the state change
            row.state = alert.state
            row.snoozed_until = alert.snoozed_until
            row.resolved_at = alert.resolved_at
            await session.commit()
            return alert
