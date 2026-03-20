from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class CanonicalFlowEvent:
    chain: str
    event_type: str
    wallet: str
    payload: Dict[str, Any]
