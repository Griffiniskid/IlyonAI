from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.api.schemas.agent import ToolEnvelope, ToolError


@dataclass
class ToolCtx:
    services: Any
    user_id: int
    wallet: str | None


def ok_envelope(*, data, card_type=None, card_payload=None):
    return ToolEnvelope(
        ok=True,
        data=data,
        card_type=card_type,
        card_id=str(uuid4()),
        card_payload=card_payload,
    )


def err_envelope(code, message, *, card_type=None):
    return ToolEnvelope(
        ok=False,
        data=None,
        card_type=card_type,
        card_id=str(uuid4()),
        card_payload=None,
        error=ToolError(code=code, message=message),
    )
