from __future__ import annotations

from typing import Any, Dict, List

from src.defi.evidence import clamp


SEVERITY_PENALTIES = {"low": 5, "medium": 10, "high": 18, "critical": 28}


def score_behavior(behavior: Dict[str, Any]) -> Dict[str, Any]:
    concentration = float(behavior.get("capital_concentration_score") or 0.0)
    anomalies = behavior.get("anomaly_flags") or []
    penalty = max(0.0, concentration - 50.0) * 0.45
    flags: List[str] = []
    kill_switches: List[str] = []
    for anomaly in anomalies:
        code = str(anomaly.get("code") or "unknown")
        severity = str(anomaly.get("severity") or "medium").lower()
        flags.append(code)
        penalty += SEVERITY_PENALTIES.get(severity, 10)
        if severity in {"high", "critical"}:
            kill_switches.append(code)
    score = clamp(88 - penalty)
    return {
        "score": score,
        "burden": clamp(100 - score),
        "fragility_flags": flags,
        "kill_switches": kill_switches,
        "haircut_penalty": min(0.45, penalty / 140.0),
        "notes": ["Behavior signals are wired into scoring, not just surfaced for display."] if anomalies or concentration else ["No adverse behavior signals materially changed the deterministic score."],
    }
