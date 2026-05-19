"""V7-020 — spec-path compatibility shim for the OpenRouter LLM client.

Spec mandates ``from src.agent.llm.openrouter_client import ...`` but the
canonical dual-provider client lives at ``src/ai/openai_client.py``.
``src/agent/llm/openrouter_client.py`` is a re-export shim. These pins
guarantee:

1. Spec-mandated imports resolve.
2. ``OpenRouterClient`` is an alias of ``OpenAIClient`` (no separate class).
3. The shim points at the canonical class object — preventing silent
   divergence between two implementations.
4. Smoke construction with ``use_openrouter=True`` flips the base_url to
   the OpenRouter chat completions endpoint.
"""
from __future__ import annotations

import pytest


def test_shim_exports_openai_client():
    """Spec-mandated import path must resolve."""
    from src.agent.llm.openrouter_client import OpenAIClient  # noqa: F401


def test_shim_exports_openrouter_client_alias():
    """Alias name must also be importable from the shim."""
    from src.agent.llm.openrouter_client import OpenRouterClient  # noqa: F401


def test_openrouter_client_is_openai_client_alias():
    """OpenRouterClient must BE OpenAIClient (identity, not just equality).

    There is no separate OpenRouter class; the dual-provider client
    selects base_url/headers via the ``use_openrouter`` flag.
    """
    from src.agent.llm.openrouter_client import OpenAIClient, OpenRouterClient

    assert OpenRouterClient is OpenAIClient


def test_shim_points_at_canonical_class():
    """Shim must re-export the canonical class object — not a copy.

    Guards against future drift where someone redefines OpenAIClient
    inside the shim and silently forks behaviour.
    """
    from src.agent.llm.openrouter_client import OpenAIClient as ShimOpenAI
    from src.ai.openai_client import OpenAIClient as CanonicalOpenAI

    assert ShimOpenAI is CanonicalOpenAI


def test_smoke_construct_openrouter_client():
    """Constructing via the shim with ``use_openrouter=True`` must flip
    base_url to the OpenRouter chat completions endpoint and set the
    flag on the instance.
    """
    from src.agent.llm.openrouter_client import OpenAIClient

    client = OpenAIClient(
        api_key="test",
        use_openrouter=True,
        model="test-model",
    )

    assert client.use_openrouter is True
    assert client.base_url == "https://openrouter.ai/api/v1/chat/completions"
    assert client.api_key == "test"
    assert client.model == "test-model"
