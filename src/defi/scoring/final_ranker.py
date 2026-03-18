from __future__ import annotations

from typing import Any


def blend_final_score(deterministic_score: int, ai_judgment_score: int, evidence_confidence: int, hard_caps: list[dict[str, Any]] | list[str]) -> int:
    ai_weight = 0.5 if evidence_confidence >= 60 else 0.2
    blended = round((deterministic_score * (1 - ai_weight)) + (ai_judgment_score * ai_weight))
    if hard_caps:
        return min(blended, deterministic_score, _hard_cap_limit(hard_caps))
    return blended


def _hard_cap_limit(hard_caps: list[dict[str, Any]] | list[str]) -> int:
    caps = [cap.get("cap") for cap in hard_caps if isinstance(cap, dict) and cap.get("cap") is not None]
    if not caps:
        return 100
    return min(int(cap) for cap in caps)


def recommend_action(final_score: int, hard_caps: list[dict[str, Any]] | list[str]) -> tuple[str, float | None]:
    if hard_caps:
        return "avoid", 0.0
    if final_score >= 82:
        return "deploy", 10.0
    if final_score >= 70:
        return "deploy_small", 5.0
    if final_score >= 55:
        return "watch", None
    return "avoid", 0.0
