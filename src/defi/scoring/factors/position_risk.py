from __future__ import annotations

from typing import Any, Dict

from src.defi.evidence import clamp


def score_position_risk(kind: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
    score = 78
    if str(candidate.get("il_risk") or "").lower() == "yes":
        score -= 22
    utilization = float(candidate.get("utilization_pct") or 0.0)
    if kind == "lending":
        score -= max(0.0, utilization - 65.0) * 0.9
    if kind == "vault":
        score -= 10
    if "crypto_crypto" in str(candidate.get("product_type") or ""):
        score -= 8
    return {"score": clamp(score), "burden": clamp(100 - score), "notes": ["Position-specific liquidation, IL, and strategy path risk."]}
