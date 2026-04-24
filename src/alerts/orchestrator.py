from dataclasses import dataclass
from typing import Dict, Any, Optional
import time

from src.alerts.models import AlertRecord
from src.platform.dead_letter_queue import DeadLetterQueue


@dataclass
class DeliveryResult:
    primary_channel: str | None
    dlq_written: bool


class AlertOrchestrator:
    def __init__(self, store, dedupe_window_seconds: int = 300):
        self.store = store
        self.dedupe_window_seconds = dedupe_window_seconds
        self._seen: Dict[str, float] = {}
        self._alert_counter = 0
        self.dead_letter_queue = DeadLetterQueue()

    def _prune_seen(self, now: float) -> None:
        expired = [
            key
            for key, timestamp in self._seen.items()
            if (now - timestamp) > self.dedupe_window_seconds
        ]
        for key in expired:
            del self._seen[key]

    def ingest(self, event: Dict[str, Any]) -> Optional[AlertRecord]:
        dedupe_key = f"{event.get('user_id')}_{event.get('rule_id')}_{event.get('subject_id')}"
        now = time.time()
        self._prune_seen(now)

        last_seen = self._seen.get(dedupe_key)
        if last_seen and (now - last_seen) < self.dedupe_window_seconds:
            return None

        self._seen[dedupe_key] = now
        self._alert_counter += 1
        alert = AlertRecord(
            id=f"a-{self._alert_counter}",
            state="new",
            severity=str(event.get("severity", "medium")),
            title=str(event.get("kind", "alert")).replace("_", " ").title(),
            user_id=event.get("user_id"),
            rule_id=event.get("rule_id"),
            subject_id=event.get("subject_id"),
            kind=event.get("kind"),
        )
        if hasattr(self.store, "add_alert"):
            self.store.add_alert(alert)
        return alert

    def deliver_alert_with_failover(
        self,
        alert: dict,
        channels: list[str],
        channel_handlers: dict[str, Any],
    ) -> DeliveryResult:
        ordered_channels = list(channels)
        if "in_app" not in ordered_channels:
            ordered_channels.append("in_app")

        dlq_written = False
        primary_channel: str | None = None

        for channel in ordered_channels:
            handler = channel_handlers.get(channel)
            if handler is None:
                continue
            try:
                handler(alert)
                primary_channel = channel
                break
            except Exception as exc:
                dlq_written = True
                self.dead_letter_queue.write(
                    {
                        "channel": channel,
                        "alert": alert,
                        "reason": str(exc),
                    }
                )

        return DeliveryResult(primary_channel=primary_channel, dlq_written=dlq_written)


_VALID_TRANSITIONS = {
    "new": "seen",
    "seen": "acknowledged",
}


def advance_alert_state(alert: AlertRecord, new_state: str) -> AlertRecord:
    expected = _VALID_TRANSITIONS.get(alert.state)
    if expected != new_state:
        raise ValueError(f"invalid transition: {alert.state} -> {new_state}")
    alert.state = new_state
    return alert
