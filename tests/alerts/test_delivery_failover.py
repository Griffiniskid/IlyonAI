from src.alerts.orchestrator import AlertOrchestrator
from src.alerts.store import InMemoryAlertStore


def test_alert_delivery_falls_back_to_in_app_and_dlq_on_channel_failure():
    store = InMemoryAlertStore()
    orchestrator = AlertOrchestrator(store=store)

    def failing_webhook(_: dict) -> None:
        raise RuntimeError("webhook down")

    delivered_in_app: list[str] = []

    def in_app_handler(alert: dict) -> None:
        delivered_in_app.append(alert["id"])

    result = orchestrator.deliver_alert_with_failover(
        alert={"id": "a-1"},
        channels=["webhook", "in_app"],
        channel_handlers={"webhook": failing_webhook, "in_app": in_app_handler},
    )

    assert result.primary_channel == "in_app"
    assert result.dlq_written is True
    assert delivered_in_app == ["a-1"]
    assert len(orchestrator.dead_letter_queue.items) == 1
