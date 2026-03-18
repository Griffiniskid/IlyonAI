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
    observability: Optional["AnalysisMetricsPayload"] = None
    error: Optional[str] = None


class OpportunityIdentity(StrictContractModel):
    id: str
    chain: str
    kind: str
    protocol_slug: str
    category: Optional[str] = None
    assets: list[str] = Field(default_factory=list)
    strategy_family: Optional[str] = None
    protocol_name: Optional[str] = None
    title: Optional[str] = None
    symbol: Optional[str] = None
    product_type: Optional[str] = None


class MarketSnapshot(StrictContractModel):
    apy: Optional[float] = None
    tvl_usd: Optional[float] = Field(default=None, ge=0)
    liquidity_usd: Optional[float] = Field(default=None, ge=0)
    volume_24h_usd: Optional[float] = Field(default=None, ge=0)
    utilization_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    volatility_30d: Optional[float] = Field(default=None, ge=0)
    market_regime: str = "unknown"


class ScoreBreakdown(StrictContractModel):
    deterministic_score: int = Field(ge=0, le=100)
    ai_judgment_score: int = Field(ge=0, le=100)
    final_deployability_score: int = Field(ge=0, le=100)
    safety_score: int = Field(ge=0, le=100)
    apr_quality_score: int = Field(ge=0, le=100)
    exit_quality_score: int = Field(ge=0, le=100)
    resilience_score: int = Field(ge=0, le=100)
    confidence_score: int = Field(ge=0, le=100)
    capped_score: Optional[int] = None
    risk_penalty: Optional[int] = None


class HardCapEffect(StrictContractModel):
    applied: bool = False
    dimension: Optional[str] = None
    capped_at: Optional[int] = Field(default=None, ge=0, le=100)
    reason: Optional[str] = None


class FactorMetadata(StrictContractModel):
    raw_measurement: Any = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    source: str = "unknown"
    freshness_hours: Optional[float] = Field(default=None, ge=0)
    hard_cap_effect: HardCapEffect = Field(default_factory=HardCapEffect)


class FactorAssessment(StrictContractModel):
    key: str
    label: str
    value: Optional[str] = None
    normalized_score: Optional[int] = Field(default=None, ge=0, le=100)
    score_impact: Optional[int] = None
    scenario_sensitivity: Optional[str] = None
    summary: str = ""
    metadata: FactorMetadata = Field(default_factory=FactorMetadata)


class BehaviorSummary(StrictContractModel):
    whale_flow_direction: str = "unknown"
    smart_money_conviction: str = "unknown"
    user_momentum: str = "unknown"
    liquidity_stability: str = "unknown"
    volatility_regime: str = "unknown"
    concentration_risk_signal: str = "unknown"
    catalyst_momentum: str = "unknown"


class ScenarioSummary(StrictContractModel):
    name: str
    outlook: str
    trigger: Optional[str] = None
    probability: Optional[str] = None


class RecommendationSummary(StrictContractModel):
    action: Literal["deploy", "deploy_small", "watch", "avoid"]
    rationale: list[str] = Field(default_factory=list)
    deployment_size_pct: Optional[float] = Field(default=None, ge=0, le=100)
    monitor_triggers: list[str] = Field(default_factory=list)


class EvidenceRecord(StrictContractModel):
    key: str
    title: str
    summary: str
    source: str = "internal"
    freshness_hours: Optional[float] = Field(default=None, ge=0)
    url: Optional[str] = None


class AnalysisMetricsPayload(StrictContractModel):
    total_latency_ms: Optional[float] = Field(default=None, ge=0)
    stage_latency_ms: dict[str, float] = Field(default_factory=dict)
    provider_stats: dict[str, dict[str, Any]] = Field(default_factory=dict)
    cache_stats: dict[str, dict[str, int]] = Field(default_factory=dict)
    enrichment_coverage_pct: Optional[float] = Field(default=None, ge=0, le=100)
    ai_runtime_ms: Optional[float] = Field(default=None, ge=0)
    ai_cost_usd: Optional[float] = Field(default=None, ge=0)
    factor_model_version: Optional[str] = None
    rank_change_reasons: list[str] = Field(default_factory=list)


class OpportunityAnalysis(StrictContractModel):
    identity: OpportunityIdentity
    market: MarketSnapshot
    scores: ScoreBreakdown
    factors: list[FactorAssessment]
    behavior: BehaviorSummary
    scenarios: list[ScenarioSummary]
    recommendation: RecommendationSummary
    evidence: list[EvidenceRecord]
    observability: Optional[AnalysisMetricsPayload] = None
