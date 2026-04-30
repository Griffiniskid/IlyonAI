from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable

from src.api.schemas.agent import ToolEnvelope
from src.scoring.bridge_scorer import score_bridge_mapping
from src.scoring.pool_scorer import score_pool_mapping
from src.scoring.route_scorer import score_route_mapping
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
    envelope.scoring_inputs = {"target": "pool", "source": raw}
    if envelope.card_payload is not None:
        envelope.card_payload = {**envelope.card_payload, "sentinel": _model_dump(sentinel)}
    return envelope


def attach_transaction_shield(envelope: ToolEnvelope, source: dict[str, Any] | None = None) -> ToolEnvelope:
    if not envelope.ok:
        return envelope
    raw = source or envelope.data or envelope.card_payload or {}
    shield = shield_for_transaction(raw)
    envelope.shield = shield
    envelope.scoring_inputs = {**(envelope.scoring_inputs or {}), "shield_source": raw}
    if envelope.card_payload is not None:
        envelope.card_payload = {**envelope.card_payload, "shield": _model_dump(shield)}
    return envelope


def attach_route_score(envelope: ToolEnvelope, source: dict[str, Any] | None = None) -> ToolEnvelope:
    if not envelope.ok:
        return envelope
    raw = source or envelope.data or envelope.card_payload or {}
    sentinel, shield = score_route_mapping(raw)
    envelope.sentinel = sentinel
    envelope.shield = shield
    envelope.scoring_inputs = {"target": "route", "source": raw}
    if envelope.card_payload is not None:
        envelope.card_payload = {
            **envelope.card_payload,
            "sentinel": _model_dump(sentinel),
            "shield": _model_dump(shield),
        }
    return envelope


def attach_bridge_score(envelope: ToolEnvelope, source: dict[str, Any] | None = None) -> ToolEnvelope:
    if not envelope.ok:
        return envelope
    raw = source or envelope.data or envelope.card_payload or {}
    sentinel, shield = score_bridge_mapping(raw)
    envelope.sentinel = sentinel
    envelope.shield = shield
    envelope.scoring_inputs = {"target": "bridge", "source": raw}
    if envelope.card_payload is not None:
        envelope.card_payload = {
            **envelope.card_payload,
            "sentinel": _model_dump(sentinel),
            "shield": _model_dump(shield),
        }
    return envelope


def _first_staking_option(envelope: ToolEnvelope) -> dict[str, Any]:
    data = envelope.data or {}
    options = data.get("staking_options") or []
    if options:
        first = dict(options[0])
        first.setdefault("project", first.get("protocol"))
        first.setdefault("symbol", first.get("asset") or first.get("token"))
        first.setdefault("tvlUsd", first.get("tvl_usd"))
        return first
    return envelope.data or envelope.card_payload or {}


def enrich_tool_envelope(tool_name: str, envelope: ToolEnvelope) -> ToolEnvelope:
    if not envelope.ok:
        return envelope
    if tool_name in {"get_defi_analytics", "find_liquidity_pool"} or envelope.card_type == "pool":
        return attach_pool_score(envelope)
    if tool_name == "get_staking_options" or envelope.card_type == "stake":
        return attach_pool_score(envelope, _first_staking_option(envelope))
    if tool_name in {"simulate_swap", "build_swap_tx", "build_solana_swap"} or envelope.card_type == "swap_quote":
        return attach_route_score(envelope)
    if tool_name == "build_bridge_tx" or envelope.card_type == "bridge":
        return attach_bridge_score(envelope)
    if tool_name in {"build_stake_tx", "build_deposit_lp_tx", "build_transfer_tx"}:
        return attach_transaction_shield(envelope)
    return envelope


def sentinel_decorator(target: str) -> Callable[[Callable[..., Awaitable[ToolEnvelope]]], Callable[..., Awaitable[ToolEnvelope]]]:
    def decorate(fn: Callable[..., Awaitable[ToolEnvelope]]) -> Callable[..., Awaitable[ToolEnvelope]]:
        @wraps(fn)
        async def wrapped(*args: Any, **kwargs: Any) -> ToolEnvelope:
            envelope = await fn(*args, **kwargs)
            if target in {"pool", "staking_option", "tx_pool"}:
                return attach_pool_score(envelope)
            if target == "route":
                return attach_route_score(envelope)
            if target == "bridge":
                return attach_bridge_score(envelope)
            if target == "tx":
                return attach_transaction_shield(envelope)
            return envelope

        return wrapped

    return decorate
