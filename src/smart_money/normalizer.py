from typing import Any, Dict
from src.smart_money.models import CanonicalFlowEvent

def normalize_event(raw: Dict[str, Any]) -> CanonicalFlowEvent:
    return CanonicalFlowEvent(
        chain=raw["chain"],
        event_type=raw["type"],
        wallet=raw["wallet"],
        payload=dict(raw),
    )
