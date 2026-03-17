import pytest
from pydantic import ValidationError

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
            "identity": {"id": "opp_1", "chain": "solana", "kind": "pool", "protocol_slug": "orca"},
            "market": {"apy": 12.4, "market_regime": "range-bound"},
            "scores": {"deterministic_score": 72, "ai_judgment_score": 68, "final_deployability_score": 70},
            "factors": [],
            "behavior": {"whale_flow_direction": "accumulating"},
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
            },
            "factors": [
                {
                    "key": "exit-liquidity",
                    "label": "Exit liquidity",
                    "value": "healthy",
                    "score_impact": 8,
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
    assert analysis.factors[0].metadata.raw_measurement == {"liquidity_usd": 1200000}
    assert analysis.factors[0].metadata.confidence == 0.84
    assert analysis.factors[0].metadata.source == "dex-screener"
    assert analysis.factors[0].metadata.freshness_hours == 1.5
    assert analysis.factors[0].metadata.hard_cap_effect.applied is True
    assert analysis.factors[0].metadata.hard_cap_effect.dimension == "exit_quality"
    assert analysis.scenarios[0].name == "base"
    assert analysis.evidence[0].source == "defillama"
