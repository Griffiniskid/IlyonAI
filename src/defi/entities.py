"""Stable DeFi domain objects used by the intelligence layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, cast


class DictModel:
    def to_dict(self) -> Dict[str, Any]:
        return asdict(cast(Any, self))


@dataclass
class RiskDimension(DictModel):
    key: str
    label: str
    score: int
    weight: float
    summary: str


@dataclass
class EvidenceItem(DictModel):
    key: str
    title: str
    summary: str
    type: str
    severity: str = "low"
    source: str = "internal"
    url: Optional[str] = None


@dataclass
class ScenarioResult(DictModel):
    key: str
    title: str
    impact: str
    severity: str
    trigger: str


@dataclass
class DependencyEdge(DictModel):
    key: str
    name: str
    dependency_type: str
    risk_score: int
    confidence_score: int
    source: str
    freshness_hours: Optional[float] = None
    notes: str = ""


@dataclass
class AssetProfile(DictModel):
    symbol: str
    role: str
    chain: str
    quality_score: int
    risk_level: str
    confidence_score: int
    source: str
    address: Optional[str] = None
    thesis: str = ""
    token_analysis: Optional[Dict[str, Any]] = None


@dataclass
class ConfidenceReport(DictModel):
    score: int
    label: str
    coverage_ratio: float
    source_count: int
    freshness_hours: Optional[float]
    partial_analysis: bool
    missing_critical_fields: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ScoreCap(DictModel):
    dimension: str
    cap: int
    reason: str


@dataclass
class HardCapEffect(DictModel):
    applied: bool = False
    dimension: Optional[str] = None
    capped_at: Optional[int] = None
    reason: Optional[str] = None


@dataclass
class FactorMetadata(DictModel):
    raw_measurement: Any = None
    confidence: Optional[float] = None
    source: str = "unknown"
    freshness_hours: Optional[float] = None
    hard_cap_effect: HardCapEffect = field(default_factory=HardCapEffect)


@dataclass
class FactorObservation(DictModel):
    key: str
    label: str
    value: Optional[str] = None
    score_impact: Optional[int] = None
    summary: str = ""
    metadata: FactorMetadata = field(default_factory=FactorMetadata)


@dataclass
class SimulationScenario(DictModel):
    name: str
    summary: str
    metric: str
    value: float
    unit: str
    severity: str


@dataclass
class SimulationResult(DictModel):
    kind: str
    summary: str
    base_case: Dict[str, Any]
    scenarios: List[Dict[str, Any]]
    recommendations: List[str]
