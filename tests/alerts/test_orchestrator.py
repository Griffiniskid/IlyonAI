import pytest
from src.alerts.store import InMemoryAlertStore
from src.alerts.orchestrator import AlertOrchestrator
from src.alerts.models import AlertRecord

def test_orchestrator_dedupes_same_alert_within_window():
    store = InMemoryAlertStore()
    orchestrator = AlertOrchestrator(store=store, dedupe_window_seconds=300)
    event = {
        "user_id": "u-1",
        "rule_id": "r-1",
        "subject_id": "token-1",
        "severity": "high",
        "kind": "whale_dump",
    }
    first = orchestrator.ingest(event)
    second = orchestrator.ingest(event)
    assert first is not None
    assert second is None


def test_store_rules_crud_and_alert_filtering():
    store = InMemoryAlertStore()

    created = store.create_rule({"name": "high-only", "severity": ["high"]})
    fetched = store.get_rule(created.id)
    assert fetched is not None
    assert fetched.name == "high-only"

    updated = store.update_rule(created.id, {"name": "critical-only", "severity": ["critical"]})
    assert updated is not None
    assert updated.name == "critical-only"

    store.add_alert(AlertRecord(id="a-1", state="new", severity="high", title="A"))
    store.add_alert(AlertRecord(id="a-2", state="new", severity="low", title="B"))
    high_alerts = store.list_alerts(severity="high")
    assert [item.id for item in high_alerts] == ["a-1"]

    assert store.delete_rule(created.id) is True
    assert store.get_rule(created.id) is None


def test_store_severity_string_is_single_value_not_character_list():
    store = InMemoryAlertStore()
    created = store.create_rule({"name": "single", "severity": "high"})
    assert created.severity == ["high"]


def test_orchestrator_prunes_expired_dedupe_entries():
    store = InMemoryAlertStore()
    orchestrator = AlertOrchestrator(store=store, dedupe_window_seconds=300)
    orchestrator._seen = {
        "old_key": 0.0,
        "fresh_key": 999999999999.0,
    }

    event = {
        "user_id": "u-1",
        "rule_id": "r-1",
        "subject_id": "token-1",
        "severity": "high",
        "kind": "whale_dump",
    }
    orchestrator.ingest(event)

    assert "old_key" not in orchestrator._seen


def test_store_alert_actions_progress_state_and_resolution():
    store = InMemoryAlertStore()
    store.add_alert(AlertRecord(id="a-9", state="new", severity="high", title="Lifecycle"))

    updated = store.apply_alert_action("a-9", "resolve")
    assert updated is not None
    assert updated.state == "acknowledged"
    assert updated.resolved_at is not None
