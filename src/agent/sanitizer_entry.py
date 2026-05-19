"""Single dedicated pre-planner sanitiser entry point.

Per spec §11 D.4: all on-chain string fields (token name, symbol, description)
MUST pass through this entry before any planner consumes them. Walks
arbitrary nested dict/list shapes and sanitises every string leaf that
matches sensitive-field keys.

Closes Part1-audit gap: "Token-string sanitiser before planner exists but
spread; no single dedicated symbol." This module is the canonical entry
point — planners and pre-LLM context builders should call
`sanitize_for_planner(payload)` on any on-chain-sourced payload.
"""
from __future__ import annotations

from typing import Any

from src.agent.sanitizer import sanitise_onchain_string


SENSITIVE_FIELDS = frozenset({
    "name", "symbol", "description", "ticker", "asset_name",
    "token_name", "token_symbol", "token_description",
    "pool_name", "pool_symbol", "protocol_name",
    "title", "summary",
})


def _sanitise_str(value: str) -> str:
    """Return the sanitised text form of an on-chain string."""
    return str(sanitise_onchain_string(value))


def sanitize_for_planner(payload: Any) -> Any:
    """Walk a nested payload, sanitise sensitive string fields.

    Returns a NEW structure; does not mutate input. Non-sensitive fields
    and non-string types pass through unchanged. Recurses through nested
    dicts and lists.
    """
    if isinstance(payload, dict):
        out: dict[Any, Any] = {}
        for k, v in payload.items():
            if k in SENSITIVE_FIELDS and isinstance(v, str):
                out[k] = _sanitise_str(v)
            else:
                out[k] = sanitize_for_planner(v)
        return out
    if isinstance(payload, list):
        return [sanitize_for_planner(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(sanitize_for_planner(item) for item in payload)
    return payload  # str/int/bool/None/float pass through
