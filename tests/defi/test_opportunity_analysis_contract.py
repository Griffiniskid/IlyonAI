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
            "scores": {"deterministic_score": 72, "ai_judgment_score": 68, "final_deployability_score": 70},
            "behavior": {"whale_flow_direction": "accumulating"},
            "recommendation": {"action": "watch", "rationale": ["need more evidence"]},
        }
    )
    assert analysis.behavior.whale_flow_direction == "accumulating"
