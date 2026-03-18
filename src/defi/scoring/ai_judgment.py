from __future__ import annotations

from typing import Any

from src.defi.ai_router import render_ai_judgment


def build_ai_judgment_score(payload: dict[str, Any]) -> dict[str, Any]:
    explanation = render_ai_judgment(payload)
    gross_apr = float(payload.get("gross_apr") or 0.0)
    risk_to_apr_ratio = float(payload.get("risk_to_apr_ratio") or 0.0)
    evidence_confidence = int(payload.get("evidence_confidence") or payload.get("confidence_score") or 70)

    score = 72
    if gross_apr >= 12:
        score += 6
    elif gross_apr <= 4:
        score -= 4
    if risk_to_apr_ratio >= 3.0:
        score -= 10
    elif risk_to_apr_ratio >= 2.0:
        score -= 5
    elif risk_to_apr_ratio <= 1.2:
        score += 5
    if evidence_confidence < 60:
        score = min(score, 65)

    explanation["judgment_score"] = max(0, min(100, int(round(score))))
    return explanation
