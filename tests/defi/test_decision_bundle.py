from src.defi.scoring.deterministic import DeterministicScorer


def test_decision_bundle_contains_expected_summary_fields():
    scorer = DeterministicScorer()
    result = scorer.score(
        kind="pool",
        candidate={"product_type": "crypto_stable_lp", "apy": 16.0, "apy_base": 12.0, "apy_reward": 4.0, "tvl_usd": 6_000_000},
        context={"protocol_safety": 76, "behavior": {}, "history": {}, "docs": {"available": True}},
    )

    summary = result["summary"]
    for key in [
        "gross_apr",
        "haircut_apr",
        "net_expected_apr",
        "weighted_risk_burden",
        "risk_to_apr_ratio",
        "fragility_flags",
        "kill_switches",
        "best_fit_risk_profile",
        "confidence_reasoning",
    ]:
        assert key in summary
