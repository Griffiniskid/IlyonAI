from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AdaptiveWeightGate:
    min_samples: int
    min_precision: float
    min_recall: float = 0.0

    def can_enable(self, *, current_samples: int, precision: float, recall: float = 0.0) -> bool:
        return (
            current_samples >= self.min_samples
            and precision >= self.min_precision
            and recall >= self.min_recall
        )


def adaptive_penalty_multiplier(
    signal_code: str,
    *,
    adaptive_penalty_weights: Mapping[str, float] | None,
    gate: AdaptiveWeightGate,
    current_samples: int,
    precision: float,
    recall: float,
) -> float:
    if not gate.can_enable(current_samples=current_samples, precision=precision, recall=recall):
        return 1.0
    if not adaptive_penalty_weights:
        return 1.0

    weight = float(adaptive_penalty_weights.get(signal_code, 1.0))
    return max(0.0, min(1.0, weight))
