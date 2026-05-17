"""Pin tests for :mod:`src.agent.intent.lp_intent_extractor` (V7-020).

Spec ref: DevPlan P1.4 — JSON-schema-constrained OpenRouter calls for
deterministic LP intent extraction.

These tests mock the OpenRouter client so they never touch the network.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest
from pydantic import ValidationError

from src.agent.intent.lp_intent_extractor import (
    LP_INTENT_SCHEMA_NAME,
    build_response_format_schema,
    extract_lp_intent,
)
from src.agent.intent.liquidity_intent import LiquidityIntent, LpAction


# ---------------------------------------------------------------------------
# Mock client
# ---------------------------------------------------------------------------


class _StubOpenRouter:
    """Minimal duck-typed OpenRouter client for tests.

    Records the kwargs it was called with so assertions can verify the
    ``response_format`` envelope was passed through. ``payload`` is the
    canned response dict (or string) it returns from ``chat_json``.
    """

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.last_kwargs: Dict[str, Any] = {}
        self.call_count = 0

    async def chat_json(
        self,
        message: str,
        system_prompt: str = "",
        max_tokens: int = 900,
        temperature: float = 0.1,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Any:
        self.call_count += 1
        self.last_kwargs = {
            "message": message,
            "system_prompt": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": response_format,
        }
        return self.payload


# ---------------------------------------------------------------------------
# Schema-builder tests
# ---------------------------------------------------------------------------


def test_build_response_format_schema_envelope_shape() -> None:
    """The envelope must use type=json_schema and the LiquidityIntent name."""
    rf = build_response_format_schema()
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "LiquidityIntent"
    assert rf["json_schema"]["name"] == LP_INTENT_SCHEMA_NAME
    assert rf["json_schema"]["strict"] is True
    assert isinstance(rf["json_schema"]["schema"], dict)


def test_build_response_format_schema_covers_all_intent_fields() -> None:
    """Every LiquidityIntent enum + amounts + slippage_bps must appear."""
    rf = build_response_format_schema()
    schema = rf["json_schema"]["schema"]
    props = schema.get("properties", {})

    # The four LP-spec §3 enums must each show up as a property.
    for field in ("action", "strategy", "range_preset", "amount_mode"):
        assert field in props, f"missing enum field: {field}"

    # Pair + amounts + slippage_bps are load-bearing for the planner.
    for field in ("pair", "amounts", "slippage_bps", "fee_tier"):
        assert field in props, f"missing field: {field}"

    # The enum definitions must be present via $defs (pydantic v2 emits
    # them there). Check at least LpAction is reachable.
    defs = schema.get("$defs", {})
    assert "LpAction" in defs
    assert set(defs["LpAction"]["enum"]) >= {"ADD", "INCREASE", "DECREASE", "CLOSE"}

    # action is required (the only required field in LiquidityIntent).
    assert "action" in schema.get("required", [])


# ---------------------------------------------------------------------------
# Extractor tests
# ---------------------------------------------------------------------------


def test_extract_lp_intent_parses_valid_payload() -> None:
    """A well-formed mock response yields a validated LiquidityIntent."""
    stub = _StubOpenRouter(
        payload={
            "action": "ADD",
            "pair": ["USDC", "WETH"],
            "fee_tier": 500,
            "slippage_bps": 50,
        }
    )
    result = asyncio.run(
        extract_lp_intent("Add USDC/WETH 0.05% pool", stub)
    )
    assert isinstance(result, LiquidityIntent)
    assert result.action == LpAction.ADD
    assert result.pair == ("USDC", "WETH")
    assert result.fee_tier == 500
    assert result.slippage_bps == 50

    # Verify the response_format envelope was actually threaded through.
    rf = stub.last_kwargs["response_format"]
    assert rf is not None
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "LiquidityIntent"
    assert stub.last_kwargs["temperature"] == 0.0
    assert stub.call_count == 1


def test_extract_lp_intent_invalid_action_raises_validation_error() -> None:
    """Bogus enum value from the LLM must raise ValidationError so the
    caller can fall back to the regex detector."""
    stub = _StubOpenRouter(
        payload={"action": "NOT_A_REAL_ACTION", "pair": ["USDC", "WETH"]}
    )
    with pytest.raises(ValidationError):
        asyncio.run(extract_lp_intent("nonsense", stub))


def test_extract_lp_intent_missing_required_raises_validation_error() -> None:
    """``action`` is the only required field — omitting it must fail."""
    stub = _StubOpenRouter(payload={"pair": ["USDC", "WETH"]})
    with pytest.raises(ValidationError):
        asyncio.run(extract_lp_intent("no action field", stub))


def test_extract_lp_intent_empty_payload_raises_value_error() -> None:
    """Empty / non-dict client output → ValueError (distinct failure mode)."""
    stub = _StubOpenRouter(payload={})
    with pytest.raises(ValueError):
        asyncio.run(extract_lp_intent("empty", stub))


def test_extract_lp_intent_handles_json_string_payload() -> None:
    """If a client returns a raw JSON string (some impls do), we still parse."""
    stub = _StubOpenRouter(
        payload='{"action": "CLOSE", "pair": ["USDC", "WETH"]}'
    )
    result = asyncio.run(extract_lp_intent("close my LP", stub))
    assert result.action == LpAction.CLOSE
    assert result.pair == ("USDC", "WETH")
