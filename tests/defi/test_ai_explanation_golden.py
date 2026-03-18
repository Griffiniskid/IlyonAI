import json
from pathlib import Path

from src.defi.ai_router import build_ai_judgment_payload, render_ai_judgment
from src.defi.scoring.ai_judgment import build_ai_judgment_score


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


def test_ai_judgment_respects_explicit_zero_evidence_confidence():
    judgment = build_ai_judgment_score(
        {
            "protocol": "curve",
            "chain": "ethereum",
            "gross_apr": 14.0,
            "risk_to_apr_ratio": 1.0,
            "evidence_confidence": 0,
        }
    )

    assert judgment["evidence_confidence"] == 0
    assert judgment["judgment_score"] == 65
