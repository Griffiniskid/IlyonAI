"""Shared test utilities."""

from src.alerts.store import InMemoryAlertStore


class AsyncInMemoryAlertStore(InMemoryAlertStore):
    """Wraps InMemoryAlertStore with async methods matching DatabaseAlertStore interface."""

    async def create_rule(self, payload):
        return super().create_rule(payload)

    async def list_rules(self):
        return super().list_rules()

    async def get_rule(self, rule_id):
        return super().get_rule(rule_id)

    async def update_rule(self, rule_id, payload):
        return super().update_rule(rule_id, payload)

    async def delete_rule(self, rule_id):
        return super().delete_rule(rule_id)

    async def add_alert(self, alert):
        return super().add_alert(alert)

    async def list_alerts(self, severity=None):
        return super().list_alerts(severity=severity)

    async def apply_alert_action(self, alert_id, action, snoozed_until=None):
        return super().apply_alert_action(alert_id, action, snoozed_until)
