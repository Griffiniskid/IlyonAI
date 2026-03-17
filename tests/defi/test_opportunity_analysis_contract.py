import pytest
from pydantic import ValidationError

from src.config import Settings
from src.defi.entities import FactorObservation
from src.defi.contracts import AnalysisStatus, OpportunityAnalysis


def test_analysis_status_carries_provisional_results_and_version():
    status = AnalysisStatus(
        analysis_id="ana_123",
        status="running",
        score_model_version="defi-v2",
        provisional_shortlist=[],
    )
    assert status.status == "running"
    assert status.score_model_version == "defi-v2"


def test_opportunity_analysis_exposes_behavior_and_recommendation_sections():
    analysis = OpportunityAnalysis.model_validate(
        {
            "identity": {
                "id": "opp_1",
                "chain": "solana",
                "kind": "pool",
                "protocol_slug": "orca",
                "category": "dex",
                "assets": ["SOL", "USDC"],
                "strategy_family": "liquidity",
            },
            "market": {"apy": 12.4, "market_regime": "range-bound"},
            "scores": {
                "deterministic_score": 72,
                "ai_judgment_score": 68,
                "final_deployability_score": 70,
                "safety_score": 74,
                "apr_quality_score": 66,
                "exit_quality_score": 71,
                "resilience_score": 69,
                "confidence_score": 77,
            },
            "factors": [],
            "behavior": {
                "whale_flow_direction": "accumulating",
                "smart_money_conviction": "building",
                "user_momentum": "improving",
                "liquidity_stability": "steady",
                "volatility_regime": "contained",
            },
            "scenarios": [],
            "recommendation": {"action": "watch", "rationale": ["need more evidence"]},
            "evidence": [],
        }
    )
    assert analysis.behavior.whale_flow_direction == "accumulating"


def test_opportunity_analysis_requires_all_top_level_sections():
    with pytest.raises(ValidationError):
        OpportunityAnalysis.model_validate(
            {
                "identity": {"id": "opp_1", "chain": "solana", "kind": "pool", "protocol_slug": "orca"},
                "scores": {
                    "deterministic_score": 72,
                    "ai_judgment_score": 68,
                    "final_deployability_score": 70,
                    "safety_score": 74,
                    "apr_quality_score": 66,
                    "exit_quality_score": 71,
                    "resilience_score": 69,
                    "confidence_score": 77,
                },
                "behavior": {"whale_flow_direction": "accumulating"},
                "recommendation": {"action": "watch", "rationale": ["need more evidence"]},
            }
        )


def test_opportunity_analysis_carries_market_factor_scenario_and_evidence_details():
    analysis = OpportunityAnalysis.model_validate(
        {
            "identity": {
                "id": "opp_2",
                "chain": "solana",
                "kind": "pool",
                "protocol_slug": "kamino",
                "protocol_name": "Kamino",
                "category": "lending",
                "assets": ["SOL", "USDC"],
                "strategy_family": "carry",
            },
            "market": {
                "apy": 19.25,
                "tvl_usd": 4800000,
                "liquidity_usd": 1200000,
                "volume_24h_usd": 340000,
                "market_regime": "risk-on",
            },
            "scores": {
                "deterministic_score": 81,
                "ai_judgment_score": 77,
                "final_deployability_score": 79,
                "safety_score": 83,
                "apr_quality_score": 75,
                "exit_quality_score": 78,
                "resilience_score": 80,
                "confidence_score": 82,
            },
            "factors": [
                {
                    "key": "exit-liquidity",
                    "label": "Exit liquidity",
                    "value": "healthy",
                    "normalized_score": 78,
                    "score_impact": 8,
                    "scenario_sensitivity": "medium",
                    "summary": "Depth is sufficient for target sizing.",
                    "metadata": {
                        "raw_measurement": {"liquidity_usd": 1200000},
                        "confidence": 0.84,
                        "source": "dex-screener",
                        "freshness_hours": 1.5,
                        "hard_cap_effect": {
                            "applied": True,
                            "dimension": "exit_quality",
                            "capped_at": 72,
                            "reason": "Liquidity remains thin for large exits.",
                        },
                    },
                }
            ],
            "behavior": {
                "whale_flow_direction": "accumulating",
                "smart_money_conviction": "building",
                "user_momentum": "improving",
                "liquidity_stability": "strengthening",
                "volatility_regime": "contained",
            },
            "scenarios": [
                {
                    "name": "base",
                    "outlook": "Yield remains stable if emissions persist.",
                    "trigger": "Current liquidity range holds",
                    "probability": "medium",
                }
            ],
            "recommendation": {
                "action": "deploy_small",
                "rationale": ["Risk-adjusted yield is attractive."],
                "monitor_triggers": ["Watch for TVL drawdown"],
            },
            "evidence": [
                {
                    "key": "tvl-trend",
                    "title": "TVL trend",
                    "summary": "TVL has recovered for three straight weeks.",
                    "source": "defillama",
                    "freshness_hours": 2.0,
                }
            ],
        }
    )

    assert analysis.market.market_regime == "risk-on"
    assert analysis.identity.category == "lending"
    assert analysis.identity.assets == ["SOL", "USDC"]
    assert analysis.identity.strategy_family == "carry"
    assert analysis.scores.safety_score == 83
    assert analysis.scores.apr_quality_score == 75
    assert analysis.scores.exit_quality_score == 78
    assert analysis.scores.resilience_score == 80
    assert analysis.scores.confidence_score == 82
    assert analysis.factors[0].normalized_score == 78
    assert analysis.factors[0].scenario_sensitivity == "medium"
    assert analysis.factors[0].metadata.raw_measurement == {"liquidity_usd": 1200000}
    assert analysis.factors[0].metadata.confidence == 0.84
    assert analysis.factors[0].metadata.source == "dex-screener"
    assert analysis.factors[0].metadata.freshness_hours == 1.5
    assert analysis.factors[0].metadata.hard_cap_effect.applied is True
    assert analysis.factors[0].metadata.hard_cap_effect.dimension == "exit_quality"
    assert analysis.scenarios[0].name == "base"
    assert analysis.evidence[0].source == "defillama"


def test_opportunity_analysis_rejects_invalid_numeric_ranges():
    with pytest.raises(ValidationError):
        OpportunityAnalysis.model_validate(
            {
                "identity": {
                    "id": "opp_3",
                    "chain": "solana",
                    "kind": "pool",
                    "protocol_slug": "orca",
                    "category": "dex",
                    "assets": ["SOL", "USDC"],
                    "strategy_family": "liquidity",
                },
                "market": {
                    "apy": 12.4,
                    "tvl_usd": -1,
                    "liquidity_usd": -5,
                    "volume_24h_usd": -10,
                    "utilization_ratio": 1.5,
                    "volatility_30d": -0.2,
                    "market_regime": "range-bound",
                },
                "scores": {
                    "deterministic_score": 101,
                    "ai_judgment_score": 68,
                    "final_deployability_score": 70,
                    "safety_score": 74,
                    "apr_quality_score": 66,
                    "exit_quality_score": 71,
                    "resilience_score": 69,
                    "confidence_score": 77,
                },
                "factors": [
                    {
                        "key": "exit-liquidity",
                        "label": "Exit liquidity",
                        "normalized_score": -1,
                        "scenario_sensitivity": "high",
                        "summary": "Invalid test case.",
                        "metadata": {
                            "raw_measurement": {"liquidity_usd": 1200000},
                            "confidence": 1.4,
                            "source": "dex-screener",
                            "freshness_hours": -2,
                            "hard_cap_effect": {
                                "applied": True,
                                "dimension": "exit_quality",
                                "capped_at": 120,
                                "reason": "Invalid cap.",
                            },
                        },
                    }
                ],
                "behavior": {
                    "whale_flow_direction": "accumulating",
                    "smart_money_conviction": "building",
                    "user_momentum": "improving",
                    "liquidity_stability": "steady",
                    "volatility_regime": "contained",
                },
                "scenarios": [],
                "recommendation": {
                    "action": "deploy_small",
                    "deployment_size_pct": 120,
                    "rationale": ["Invalid test case."],
                },
                "evidence": [
                    {
                        "key": "bad-evidence",
                        "title": "Bad freshness",
                        "summary": "Invalid freshness.",
                        "freshness_hours": -1,
                    }
                ],
            }
        )


def test_defi_runtime_settings_reject_nonsensical_values():
    with pytest.raises(ValidationError):
        Settings(
            defi_scan_limit=0,
            defi_top_band_limit=0,
            defi_provider_timeout_seconds=0,
            defi_analysis_ttl_seconds=-1,
        )


def test_factor_observation_supports_expanded_factor_fields():
    observation = FactorObservation(
        key="exit-liquidity",
        label="Exit liquidity",
        normalized_score=78,
        scenario_sensitivity="medium",
        summary="Depth is sufficient for target sizing.",
    )

    assert observation.normalized_score == 78
    assert observation.scenario_sensitivity == "medium"
