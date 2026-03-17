"""Pydantic contracts for DeFi opportunity analysis payloads."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisStatus(StrictContractModel):
    analysis_id: str
    status: Literal["queued", "running", "completed", "failed"]
    score_model_version: str
    provisional_shortlist: list[dict[str, Any]] = Field(default_factory=list)


class OpportunityIdentity(StrictContractModel):
    id: str
    chain: str
    kind: str
    protocol_slug: str
    protocol_name: Optional[str] = None
    title: Optional[str] = None
    symbol: Optional[str] = None
    product_type: Optional[str] = None


class MarketSnapshot(StrictContractModel):
    apy: Optional[float] = None
    tvl_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    utilization_ratio: Optional[float] = None
    volatility_30d: Optional[float] = None
    market_regime: str = "unknown"


class ScoreBreakdown(StrictContractModel):
    deterministic_score: int
    ai_judgment_score: int
    final_deployability_score: int
    confidence_score: Optional[int] = None
    capped_score: Optional[int] = None
    risk_penalty: Optional[int] = None


class HardCapEffect(StrictContractModel):
    applied: bool = False
    dimension: Optional[str] = None
    capped_at: Optional[int] = None
    reason: Optional[str] = None


class FactorMetadata(StrictContractModel):
    raw_measurement: Any = None
    confidence: Optional[float] = None
    source: str = "unknown"
    freshness_hours: Optional[float] = None
    hard_cap_effect: HardCapEffect = Field(default_factory=HardCapEffect)


class FactorAssessment(StrictContractModel):
    key: str
    label: str
    value: Optional[str] = None
    score_impact: Optional[int] = None
    summary: str = ""
    metadata: FactorMetadata = Field(default_factory=FactorMetadata)


class BehaviorSummary(StrictContractModel):
    whale_flow_direction: str = "unknown"
    smart_money_conviction: str = "unknown"
    user_momentum: str = "unknown"


class ScenarioSummary(StrictContractModel):
    name: str
    outlook: str
    trigger: Optional[str] = None
    probability: Optional[str] = None


class RecommendationSummary(StrictContractModel):
    action: Literal["deploy", "deploy_small", "watch", "avoid"]
    rationale: list[str] = Field(default_factory=list)
    deployment_size_pct: Optional[float] = None
    monitor_triggers: list[str] = Field(default_factory=list)


class EvidenceRecord(StrictContractModel):
    key: str
    title: str
    summary: str
    source: str = "internal"
    freshness_hours: Optional[float] = None
    url: Optional[str] = None


class OpportunityAnalysis(StrictContractModel):
    identity: OpportunityIdentity
    market: MarketSnapshot
    scores: ScoreBreakdown
    factors: list[FactorAssessment]
    behavior: BehaviorSummary
    scenarios: list[ScenarioSummary]
    recommendation: RecommendationSummary
    evidence: list[EvidenceRecord]
