"""Run the adversarial NLU corpus through detect_intent.

Each row in tests/nlu/corpus.yaml asserts that the regex/heuristic detector
either produces the expected tool call or returns None (so the LLM/tool path
gets a clean refuse signal). Failures here block the merge.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.agent.simple_runtime import detect_intent


_CORPUS = Path(__file__).parent / "corpus.yaml"


def _load_cases() -> list[dict]:
    with _CORPUS.open() as f:
        doc = yaml.safe_load(f) or {}
    return list(doc.get("cases") or [])


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_nlu_corpus(case: dict) -> None:
    detected = detect_intent(case["input"])
    expected_tool = case.get("expect_tool")

    if expected_tool is None:
        assert detected is None, (
            f"[{case['id']}] expected no detection but got {detected!r}.\n"
            f"input: {case['input']!r}\n"
            f"reason: {case.get('description')}"
        )
        return

    assert detected is not None, (
        f"[{case['id']}] expected tool {expected_tool!r} but detector returned None.\n"
        f"input: {case['input']!r}"
    )
    tool_name, params = detected
    assert tool_name == expected_tool, (
        f"[{case['id']}] expected tool {expected_tool!r} but got {tool_name!r}\n"
        f"params: {params!r}\n"
        f"input: {case['input']!r}"
    )

    if "expect_token_in" in case:
        actual = params.get("token_in")
        assert actual == case["expect_token_in"], (
            f"[{case['id']}] expected token_in={case['expect_token_in']} got {actual}"
        )
    if "expect_token_out" in case:
        actual = params.get("token_out")
        # build_bridge_tx leaves token_out empty for resolver — accept "" / None / match
        if expected_tool == "build_bridge_tx" and actual in ("", None):
            pass
        else:
            assert actual == case["expect_token_out"], (
                f"[{case['id']}] expected token_out={case['expect_token_out']} got {actual}"
            )
    if "expect_chain_id" in case:
        actual = params.get("chain_id") or params.get("src_chain_id")
        assert actual == case["expect_chain_id"], (
            f"[{case['id']}] expected chain_id={case['expect_chain_id']} got {actual}"
        )
