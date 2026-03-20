from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any, Dict


@dataclass
class EventEnvelope:
    event_id: str
    event_type: str
    trace_id: str
    occurred_at: str
    payload: dict
    freshness: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, str):
            raise ValueError("occurred_at must be an ISO-8601 string")

        normalized = self.occurred_at.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("occurred_at must be a valid ISO-8601 timestamp") from exc
