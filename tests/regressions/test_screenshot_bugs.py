"""Run regression fixtures captured from real-user bug screenshots.

Each entry in `tests/regressions/screenshots.yaml` is exercised through
`detect_intent`. A bug fix must include a new entry here BEFORE landing.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.agent.simple_runtime import detect_intent


_FIXTURES = Path(__file__).parent / "screenshots.yaml"


def _load_cases() -> list[dict]:
    with _FIXTURES.open() as f:
        doc = yaml.safe_load(f) or {}
    return list(doc.get("cases") or [])


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_screenshot_regression(case: dict) -> None:
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
        f"[{case['id']}] expected tool {expected_tool!r}, got None.\n"
        f"input: {case['input']!r}"
    )
    tool_name, params = detected
    assert tool_name == expected_tool, (
        f"[{case['id']}] expected {expected_tool}, got {tool_name}\n"
        f"params: {params!r}\ninput: {case['input']!r}"
    )

    if "expect_token_in" in case:
        assert params.get("token_in") == case["expect_token_in"]
    if "expect_token_out" in case:
        actual = params.get("token_out")
        if expected_tool == "build_bridge_tx" and actual in ("", None):
            pass
        else:
            assert actual == case["expect_token_out"]
    if "expect_chain_id" in case:
        actual = params.get("chain_id") or params.get("src_chain_id")
        assert actual == case["expect_chain_id"]
