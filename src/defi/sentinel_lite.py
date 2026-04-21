from __future__ import annotations
from typing import Optional


def sentinel_lite(shield_verdict: Optional[dict] = None, pool_sentinel: Optional[int] = None) -> dict:
    """One-score projection for the tokens ticker bar."""
    shield_score = 50  # default neutral
    if shield_verdict:
        grade_map = {"A+": 95, "A": 85, "B": 70, "C": 50, "D": 30, "F": 10}
        shield_score = grade_map.get(shield_verdict.get("grade", "C"), 50)

    score = min(shield_score, pool_sentinel) if pool_sentinel is not None else shield_score
    score = max(0, min(100, score))

    if score >= 75:
        badge = "safe"
    elif score >= 50:
        badge = "caution"
    else:
        badge = "risky"

    return {"score": score, "badge": badge}
