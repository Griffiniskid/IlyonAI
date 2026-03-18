from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class SignalFlag:
    code: str
    severity: str
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EntityHeuristic:
    code: str
    severity: str
    confidence: float = 0.0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BehaviorSignals:
    whale_flow_direction: str = "neutral"
    capital_concentration_score: float = 0.0
    wallet_stickiness_score: float = 0.0
    anomaly_flags: List[SignalFlag] = field(default_factory=list)
    entity_heuristics: List[EntityHeuristic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "whale_flow_direction": self.whale_flow_direction,
            "capital_concentration_score": self.capital_concentration_score,
            "wallet_stickiness_score": self.wallet_stickiness_score,
            "anomaly_flags": [flag.to_dict() for flag in self.anomaly_flags],
            "entity_heuristics": [heuristic.to_dict() for heuristic in self.entity_heuristics],
        }
