from __future__ import annotations

from typing import Any, Dict

from src.defi.evidence import clamp


def score_market_structure(kind: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
    product_type = str(candidate.get("product_type") or "")
    score = 58
    if "stable" in product_type:
        score += 26
    elif "crypto_stable" in product_type:
        score += 12
    elif kind == "lending":
        score += 18
    elif kind == "vault":
        score += 8
    if str(candidate.get("il_risk") or "").lower() == "yes":
        score -= 14
    reward_share = max(float(candidate.get("apy_reward") or 0.0), 0.0) / max(float(candidate.get("apy") or candidate.get("apy_supply") or 0.0), 0.01)
    score -= reward_share * 14
    return {"score": clamp(score), "burden": clamp(100 - score), "notes": ["Exposure mix, IL drag, and emissions dependence."]}
