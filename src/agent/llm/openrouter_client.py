"""V7-020 spec-path compatibility shim — re-exports the canonical
OpenAI/OpenRouter dual-provider client from src.ai.openai_client.

The spec mandates `from src.agent.llm.openrouter_client import ...`. Our
canonical implementation lives at src/ai/openai_client.py:OpenAIClient
because the same class drives both providers via the `use_openrouter`
constructor flag. This shim exists so spec-style imports work without
duplicating logic.

To instantiate an OpenRouter-specific client:
    from src.agent.llm.openrouter_client import OpenAIClient
    client = OpenAIClient(api_key=..., use_openrouter=True, ...)

There is no separate OpenRouter class — the flag selects base_url and
referer headers internally.
"""
from src.ai.openai_client import OpenAIClient

# A clearer alias for callers that want explicit semantics in their code.
OpenRouterClient = OpenAIClient

__all__ = ["OpenAIClient", "OpenRouterClient"]
