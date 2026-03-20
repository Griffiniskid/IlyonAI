from __future__ import annotations

from typing import Any, Dict, List

from src.defi.evidence import clamp
from src.quality.heuristic_weights import AdaptiveWeightGate, adaptive_penalty_multiplier


SEVERITY_PENALTIES = {"low": 5, "medium": 10, "high": 18, "critical": 28}


def score_behavior(behavior: Dict[str, Any]) -> Dict[str, Any]:
    concentration = float(behavior.get("capital_concentration_score") or 0.0)
    anomalies = behavior.get("anomaly_flags") or []
    adaptive_weights = behavior.get("adaptive_penalty_weights") or {}
    adaptive_gate_cfg = behavior.get("adaptive_gate") or {}
    adaptive_metrics = behavior.get("adaptive_metrics") or {}
    gate = AdaptiveWeightGate(
        min_samples=int(adaptive_gate_cfg.get("min_samples") or 0),
        min_precision=float(adaptive_gate_cfg.get("min_precision") or 0.0),
        min_recall=float(adaptive_gate_cfg.get("min_recall") or 0.0),
    )
    current_samples = int(adaptive_metrics.get("current_samples") or 0)
    precision = float(adaptive_metrics.get("precision") or 0.0)
    recall = float(adaptive_metrics.get("recall") or 0.0)
    penalty = max(0.0, concentration - 50.0) * 0.45
    flags: List[str] = []
    kill_switches: List[str] = []
    for anomaly in anomalies:
        code = str(anomaly.get("code") or "unknown")
        severity = str(anomaly.get("severity") or "medium").lower()
        flags.append(code)
        penalty += SEVERITY_PENALTIES.get(severity, 10) * adaptive_penalty_multiplier(
            code,
            adaptive_penalty_weights=adaptive_weights,
            gate=gate,
            current_samples=current_samples,
            precision=precision,
            recall=recall,
        )
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
