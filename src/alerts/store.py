from __future__ import annotations

from typing import Optional
from datetime import UTC, datetime

from src.alerts.models import AlertRecord, AlertRule
from src.alerts.orchestrator import advance_alert_state


class InMemoryAlertStore:
    def __init__(self):
        self._rules: dict[str, AlertRule] = {}
        self._alerts: list[AlertRecord] = []
        self._rule_counter = 0

    @staticmethod
    def _normalize_severity(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []

    async def create_rule(self, payload: dict) -> AlertRule:
        self._rule_counter += 1
        rule = AlertRule(
            id=f"r-{self._rule_counter}",
            name=str(payload.get("name", "unnamed")),
            severity=self._normalize_severity(payload.get("severity", [])),
        )
        self._rules[rule.id] = rule
        return rule

    async def list_rules(self) -> list[AlertRule]:
        return list(self._rules.values())

    async def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        return self._rules.get(rule_id)

    async def update_rule(self, rule_id: str, payload: dict) -> Optional[AlertRule]:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        updated = current.model_copy(
            update={
                "name": payload.get("name", current.name),
                "severity": self._normalize_severity(payload.get("severity", current.severity)),
            }
        )
        self._rules[rule_id] = updated
        return updated

    async def delete_rule(self, rule_id: str) -> bool:
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        return True

    async def add_alert(self, alert: AlertRecord) -> AlertRecord:
        self._alerts.append(alert)
        return alert

    async def list_alerts(self, severity: str | None = None) -> list[AlertRecord]:
        if severity is None:
            return list(self._alerts)
        return [alert for alert in self._alerts if alert.severity == severity]

    async def get_alert(self, alert_id: str) -> Optional[AlertRecord]:
        for alert in self._alerts:
            if alert.id == alert_id:
                return alert
        return None

    async def apply_alert_action(self, alert_id: str, action: str, snoozed_until: str | None = None) -> Optional[AlertRecord]:
        alert = await self.get_alert(alert_id)
        if alert is None:
            return None

        if action == "seen":
            if alert.state == "new":
                advance_alert_state(alert, "seen")
            return alert

        if action == "acknowledge":
            if alert.state == "new":
                advance_alert_state(alert, "seen")
            if alert.state == "seen":
                advance_alert_state(alert, "acknowledged")
            return alert

        if action == "snooze":
            alert.snoozed_until = snoozed_until
            return alert

        if action == "resolve":
            if alert.state == "new":
                advance_alert_state(alert, "seen")
            if alert.state == "seen":
                advance_alert_state(alert, "acknowledged")
            alert.resolved_at = datetime.now(UTC).isoformat()
            return alert

        if action == "unsnooze":
            alert.snoozed_until = None
            return alert

        raise ValueError(f"unsupported action: {action}")
