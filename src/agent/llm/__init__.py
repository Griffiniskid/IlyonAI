"""V7-020 spec-path package — re-exports the canonical OpenAI/OpenRouter
dual-provider client from ``src.ai.openai_client``.

The IlyonAi LP Execution Spec mandates ``src/agent/llm/openrouter_client.py``
as the LLM client location. Our canonical implementation lives at
``src/ai/openai_client.py`` because a single ``OpenAIClient`` class drives
both providers via the ``use_openrouter`` constructor flag. This package
exists so spec-style imports work without duplicating logic.
"""
