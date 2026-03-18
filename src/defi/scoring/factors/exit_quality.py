from __future__ import annotations

from typing import Any, Dict

from src.defi.evidence import clamp


def score_exit_quality(kind: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
    tvl = float(candidate.get("tvl_usd") or candidate.get("tvlUsd") or 0.0)
    volume = float(candidate.get("volume_usd_1d") or candidate.get("volumeUsd1d") or 0.0)
    utilization = float(candidate.get("utilization_pct") or 0.0)
    score = 28
    if tvl > 0:
        score += min(42.0, 10.0 * (len(str(int(max(tvl, 1)))) - 4))
    if volume > 0:
        score += min(22.0, volume / max(tvl, 1.0) * 20.0)
    if kind == "lending":
        score -= max(0.0, utilization - 70.0) * 1.0
    return {"score": clamp(score), "burden": clamp(100 - score), "notes": ["TVL depth, flow, and reserve slack drive exit quality."]}
