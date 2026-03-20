from src.defi.scoring.factors.behavior import score_behavior
from src.quality.heuristic_weights import AdaptiveWeightGate


def test_adaptive_downweighting_only_enabled_after_gate_thresholds():
    gate = AdaptiveWeightGate(min_samples=200, min_precision=0.55)

    assert gate.can_enable(current_samples=50, precision=0.70, recall=0.70) is False
    assert gate.can_enable(current_samples=250, precision=0.70, recall=0.70) is True


def test_behavior_penalty_is_not_downweighted_until_gate_opens():
    baseline = score_behavior(
        {
            "anomaly_flags": [{"code": "sell_pressure_buildup", "severity": "critical"}],
            "adaptive_penalty_weights": {"sell_pressure_buildup": 0.25},
            "adaptive_gate": {"min_samples": 200, "min_precision": 0.55},
            "adaptive_metrics": {"current_samples": 50, "precision": 0.80, "recall": 0.80},
        }
    )
    downweighted = score_behavior(
        {
            "anomaly_flags": [{"code": "sell_pressure_buildup", "severity": "critical"}],
            "adaptive_penalty_weights": {"sell_pressure_buildup": 0.25},
            "adaptive_gate": {"min_samples": 200, "min_precision": 0.55},
            "adaptive_metrics": {"current_samples": 250, "precision": 0.80, "recall": 0.80},
        }
    )

    assert downweighted["score"] > baseline["score"]
