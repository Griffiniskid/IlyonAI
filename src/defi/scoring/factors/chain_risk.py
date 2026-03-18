from __future__ import annotations

from typing import Any, Dict

from src.defi.evidence import clamp


CHAIN_BASELINES = {
    "ethereum": 86,
    "base": 76,
    "arbitrum": 78,
    "optimism": 77,
    "polygon": 72,
}


def score_chain_risk(candidate: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    if context.get("chain_risk_score") is not None:
        raw_score = context.get("chain_risk_score")
        score = float(raw_score) if isinstance(raw_score, (int, float, str)) else 70.0
    else:
        score = CHAIN_BASELINES.get(str(candidate.get("chain") or "").lower(), 70)
    return {"score": clamp(score), "burden": clamp(100 - score), "notes": ["Chain operational and settlement baseline."]}
