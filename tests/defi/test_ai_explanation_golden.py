import json
from pathlib import Path

from src.defi.ai_router import build_ai_judgment_payload, render_ai_judgment


def test_ai_explanation_matches_golden_headline():
    fixture = json.loads(
        Path("tests/fixtures/defi/ai_judgment_golden.json").read_text(encoding="utf-8")
    )

    payload = build_ai_judgment_payload(
        protocol="aave-v3",
        chain="base",
        gross_apr=5.2,
        risk_to_apr_ratio=3.1,
    )

    explanation = render_ai_judgment(payload)

    assert explanation["headline"] == fixture["base_aave_supply_headline"]
    assert explanation["summary"] == fixture["base_aave_supply_summary"]
