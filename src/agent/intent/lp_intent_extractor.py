"""LP intent extractor — JSON-schema-constrained decoding via OpenRouter.

Spec ref: ``IlyonAi_Development_Plan_v2.md`` P1.4 — wraps the OpenRouter
client with structured outputs (``response_format={"type": "json_schema",
...}``) so the model is forced to emit a JSON object conforming to the
:class:`~src.agent.intent.liquidity_intent.LiquidityIntent` envelope.

Why this matters: free-form LLM JSON is brittle — fields drift, enums
get spelled wrong, types swap. Schema-constrained decoding pushes the
parsing burden onto the provider and yields deterministic, pydantic-
validatable LP intents.

The OpenRouter / OpenAI ``json_schema`` envelope shape is::

    {
        "type": "json_schema",
        "json_schema": {
            "name": "LiquidityIntent",
            "strict": True,
            "schema": { ...pydantic json schema... }
        }
    }

See https://openrouter.ai/docs/features/structured-outputs.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Protocol

from .liquidity_intent import LiquidityIntent


__all__ = [
    "build_response_format_schema",
    "extract_lp_intent",
    "LP_INTENT_SCHEMA_NAME",
]


# Public name used by both the response_format envelope and downstream
# log lines. Kept as a module-level constant so call sites can pattern-
# match on it without importing the helper.
LP_INTENT_SCHEMA_NAME = "LiquidityIntent"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_response_format_schema() -> Dict[str, Any]:
    """Build the OpenRouter ``response_format`` envelope for LiquidityIntent.

    Uses :py:meth:`LiquidityIntent.model_json_schema` (pydantic v2) so the
    schema stays in sync with the model. Wraps it in the
    ``{"type": "json_schema", "json_schema": {...}}`` shape that
    OpenRouter / OpenAI-compatible providers expect for strict structured
    decoding.

    Returns:
        Dict ready to drop into the chat-completions request body as
        ``response_format=...``.
    """
    schema = LiquidityIntent.model_json_schema()
    return {
        "type": "json_schema",
        "json_schema": {
            "name": LP_INTENT_SCHEMA_NAME,
            "strict": True,
            "schema": schema,
        },
    }


class _SupportsChatJson(Protocol):
    """Duck-typed OpenRouter / OpenAI client protocol.

    Implementations need only a ``chat_json`` coroutine that accepts a
    ``response_format`` kwarg and returns a dict parsed from the model's
    JSON output. ``src.ai.openai_client.OpenAIClient.chat_json`` matches.
    """

    async def chat_json(
        self,
        message: str,
        system_prompt: str = ...,
        max_tokens: int = ...,
        temperature: float = ...,
        response_format: Dict[str, Any] | None = ...,
    ) -> Dict[str, Any]: ...


_DEFAULT_SYSTEM_PROMPT = (
    "You extract a structured liquidity-provision (LP) intent from a "
    "user prompt. Respond with a single JSON object that conforms to the "
    "LiquidityIntent schema. Use the enum values exactly. Omit fields the "
    "user did not specify. Do not invent amounts, fee tiers, or pairs."
)


async def extract_lp_intent(
    prompt: str,
    openrouter_client: _SupportsChatJson,
    *,
    system_prompt: str | None = None,
    max_tokens: int = 900,
    temperature: float = 0.0,
) -> LiquidityIntent:
    """Extract a typed :class:`LiquidityIntent` from a free-form prompt.

    Args:
        prompt: User message describing the LP action.
        openrouter_client: Duck-typed client with an ``async chat_json``
            method (see :class:`_SupportsChatJson`).
        system_prompt: Optional override for the schema-binding system
            prompt; sensible default used otherwise.
        max_tokens: Completion budget. LP intents are tiny, but reasoning
            models need headroom.
        temperature: Defaults to ``0.0`` for deterministic extraction.

    Returns:
        A validated :class:`LiquidityIntent`.

    Raises:
        pydantic.ValidationError: if the model's JSON does not match the
            envelope (callers can fall back to the regex-based detector).
        ValueError: if the client returned a non-dict / empty payload, so
            the failure mode is distinguishable from a schema mismatch.
    """
    response_format = build_response_format_schema()
    raw = await openrouter_client.chat_json(
        prompt,
        system_prompt=system_prompt or _DEFAULT_SYSTEM_PROMPT,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
    )

    # chat_json already runs _extract_json_from_text on the model output;
    # some mock clients may return a JSON string instead — normalise.
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LP intent extractor: client returned non-JSON string: {exc}"
            ) from exc

    if not isinstance(raw, dict) or not raw:
        raise ValueError(
            "LP intent extractor: client returned empty / non-dict payload"
        )

    return LiquidityIntent.model_validate(raw)
