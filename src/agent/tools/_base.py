"""Lightweight tool context and envelope helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from src.api.schemas.agent import ToolEnvelope


@dataclass
class ToolCtx:
    """Runtime context passed to every tool and decorator."""
    services: Any = None
    user_id: Optional[int] = None
    wallet: Optional[str] = None
    session_id: Optional[str] = None
    extra: dict = field(default_factory=dict)


def ok_envelope(
    *,
    data: dict[str, Any],
    card_type: Optional[str] = None,
    card_payload: Optional[dict] = None,
) -> ToolEnvelope:
    """Build a successful ToolEnvelope."""
    return ToolEnvelope(
        ok=True,
        data=data,
        card_type=card_type,
        card_id=str(uuid4()),
        card_payload=card_payload,
    )
