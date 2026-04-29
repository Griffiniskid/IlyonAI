from __future__ import annotations

from typing import Any

from src.api.schemas.agent import ToolEnvelope
from src.scoring.pool_scorer import score_pool_mapping
from src.scoring.shield_gate import shield_for_transaction


def _model_dump(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(obj)


def attach_pool_score(envelope: ToolEnvelope, source: dict[str, Any] | None = None) -> ToolEnvelope:
    if not envelope.ok:
        return envelope
    raw = source or envelope.data or envelope.card_payload or {}
    sentinel = score_pool_mapping(raw)
    envelope.sentinel = sentinel
    if envelope.card_payload is not None:
        envelope.card_payload = {**envelope.card_payload, "sentinel": _model_dump(sentinel)}
    return envelope


def attach_transaction_shield(envelope: ToolEnvelope, source: dict[str, Any] | None = None) -> ToolEnvelope:
    if not envelope.ok:
        return envelope
    raw = source or envelope.data or envelope.card_payload or {}
    shield = shield_for_transaction(raw)
    envelope.shield = shield
    if envelope.card_payload is not None:
        envelope.card_payload = {**envelope.card_payload, "shield": _model_dump(shield)}
    return envelope
