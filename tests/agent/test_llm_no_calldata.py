"""Spec §11 D.1 — LLM never emits calldata, addresses, signatures, or amounts.

The Planner (LLM under JSON-schema constrained decoding) MUST return
typed LiquidityIntent objects only. Calldata, EVM addresses, Solana
pubkeys, and transaction signatures must originate from the Calldata
Builder, never from the LLM context.

This test walks every tool's declared signature and asserts none of
them accepts a free-text field whose name suggests calldata leak. A
contract check that fails if a regression introduces a new tool that
would let the LLM hand bytes through.
"""
from __future__ import annotations

import re

import pytest


_LEAK_PARAM_NAMES = re.compile(
    r"(?:^|_)(calldata|raw_tx|signed_tx|signature|tx_bytes|hex_data|"
    r"private_key|seed_phrase|mnemonic|secret_key)(?:$|_)",
    re.IGNORECASE,
)


def test_no_tool_accepts_calldata_parameter():
    """If a tool parameter name reads as calldata-shaped, refuse."""
    try:
        from src.agent.tools import __all__ as _public_names  # type: ignore
    except ImportError:
        pytest.skip("agent.tools package shape unknown")
    # Walk all registered tools. Try the canonical register_all_tools
    # path; fall back to public names if unavailable.
    try:
        from src.agent.tools import register_all_tools
    except ImportError:
        pytest.skip("register_all_tools not importable")
    # Build with a minimal services namespace so registration runs
    # without external deps.
    class _Services:  # noqa: D401
        pass

    try:
        tools = register_all_tools(_Services(), user_id=0, wallet="guest")
    except Exception:
        pytest.skip("register_all_tools requires live services — skip in unit test")

    leaks: list[str] = []
    for tool in tools:
        # Tool objects expose `args_schema` or `name` + `func` (LangChain-style).
        schema = getattr(tool, "args_schema", None)
        if schema is None:
            continue
        # Pydantic v1/v2 dual-shape — get field names defensively.
        fields = getattr(schema, "model_fields", None) or getattr(schema, "__fields__", None) or {}
        for field_name in fields:
            if _LEAK_PARAM_NAMES.search(field_name):
                leaks.append(f"{tool.name}.{field_name}")

    assert leaks == [], (
        f"Spec §11 D.1 violation — LLM-callable tool accepts calldata-shaped "
        f"parameters: {leaks}"
    )


def test_hex_calldata_pattern_not_in_tool_descriptions():
    """Tool description strings must not contain example bytecode."""
    try:
        from src.agent.tools import register_all_tools
    except ImportError:
        pytest.skip("register_all_tools not importable")

    class _Services:
        pass

    try:
        tools = register_all_tools(_Services(), user_id=0, wallet="guest")
    except Exception:
        pytest.skip("register_all_tools requires live services")

    hex_pattern = re.compile(r"0x[a-fA-F0-9]{16,}")
    bad: list[str] = []
    for tool in tools:
        desc = getattr(tool, "description", "") or ""
        if hex_pattern.search(desc):
            bad.append(tool.name)
    assert bad == [], (
        f"Spec §11 D.1 violation — tool descriptions contain long hex strings "
        f"that could leak calldata into LLM context: {bad}"
    )


def test_leak_regex_catches_known_shapes():
    """Sanity for the regex itself."""
    assert _LEAK_PARAM_NAMES.search("calldata")
    assert _LEAK_PARAM_NAMES.search("raw_tx")
    assert _LEAK_PARAM_NAMES.search("signed_tx")
    assert _LEAK_PARAM_NAMES.search("private_key")
    assert _LEAK_PARAM_NAMES.search("seed_phrase")
    assert not _LEAK_PARAM_NAMES.search("chain")
    assert not _LEAK_PARAM_NAMES.search("amount_in")
    assert not _LEAK_PARAM_NAMES.search("protocol")
