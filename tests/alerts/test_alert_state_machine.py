import pytest
from src.alerts.models import AlertRecord
from src.alerts.orchestrator import advance_alert_state

def test_alert_state_machine_transitions_in_order():
    alert = AlertRecord(id="a-1", state="new", severity="high", title="Whale dump")
    alert = advance_alert_state(alert, "seen")
    alert = advance_alert_state(alert, "acknowledged")
    assert alert.state == "acknowledged"


def test_alert_state_machine_rejects_invalid_transition():
    alert = AlertRecord(id="a-1", state="new", severity="high", title="Whale dump")
    with pytest.raises(ValueError):
        advance_alert_state(alert, "acknowledged")
