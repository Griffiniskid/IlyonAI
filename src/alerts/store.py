from __future__ import annotations

from typing import Optional

from src.alerts.models import AlertRecord, AlertRule


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

    def create_rule(self, payload: dict) -> AlertRule:
        self._rule_counter += 1
        rule = AlertRule(
            id=f"r-{self._rule_counter}",
            name=str(payload.get("name", "unnamed")),
            severity=self._normalize_severity(payload.get("severity", [])),
        )
        self._rules[rule.id] = rule
        return rule

    def list_rules(self) -> list[AlertRule]:
        return list(self._rules.values())

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        return self._rules.get(rule_id)

    def update_rule(self, rule_id: str, payload: dict) -> Optional[AlertRule]:
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

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        return True

    def add_alert(self, alert: AlertRecord) -> AlertRecord:
        self._alerts.append(alert)
        return alert

    def list_alerts(self, severity: str | None = None) -> list[AlertRecord]:
        if severity is None:
            return list(self._alerts)
        return [alert for alert in self._alerts if alert.severity == severity]
