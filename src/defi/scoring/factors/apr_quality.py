from __future__ import annotations

from typing import Any, Dict

from src.defi.evidence import clamp


def score_apr_quality(candidate: Dict[str, Any], history: Dict[str, Any]) -> Dict[str, Any]:
    gross_apr = float(candidate.get("apy") or candidate.get("apy_supply") or 0.0)
    apy_base = float(candidate.get("apy_base") or candidate.get("apy_supply") or gross_apr)
    apy_reward = float(candidate.get("apy_reward") or 0.0)
    reward_share = max(0.0, apy_reward) / max(gross_apr, 0.01)
    fee_share = max(0.0, min(1.0, apy_base / max(gross_apr, 0.01)))
    persistence = float(history.get("apy_persistence_score", 55 if history.get("available") else 48))
    trend = float(history.get("apy_trend_score", 55 if history.get("available") else 48))
    score = (fee_share * 58) + ((1.0 - reward_share) * 14) + (persistence * 0.16) + (trend * 0.12)
    if gross_apr > 40:
        score -= min(18.0, (gross_apr - 40.0) * 0.22)
    haircut_penalty = min(0.72, 0.10 + (reward_share * 0.34) + max(0.0, 50.0 - persistence) / 200.0)
    return {
        "score": clamp(score),
        "burden": clamp(100 - score),
        "gross_apr": round(gross_apr, 2),
        "fee_share": fee_share,
        "reward_share": reward_share,
        "haircut_penalty": haircut_penalty,
        "notes": ["APR quality rewards fee-backed carry and penalizes emissions-heavy yield."] if reward_share > 0.35 else ["APR quality benefits from organic carry and steadier history."],
    }
