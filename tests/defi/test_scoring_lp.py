from src.defi.scoring.deterministic import DeterministicScorer


def test_lp_scoring_returns_haircut_apr_and_risk_to_apr_ratio():
    scorer = DeterministicScorer()
    result = scorer.score(
        kind="pool",
        candidate={
            "product_type": "stable_lp",
            "apy": 8.0,
            "apy_base": 6.0,
            "apy_reward": 2.0,
            "tvl_usd": 8_000_000,
            "volume_usd_1d": 4_000_000,
        },
        context={
            "protocol_safety": 78,
            "behavior": {
                "capital_concentration_score": 82,
                "anomaly_flags": [{"code": "liquidity_drain", "severity": "high"}],
            },
            "history": {"available": True, "apy_persistence_score": 72, "tvl_trend_score": 75},
            "docs": {"available": True, "freshness_hours": 4},
        },
    )

    assert result["summary"]["gross_apr"] == 8.0
    assert result["summary"]["haircut_apr"] < 8.0
    assert result["summary"]["net_expected_apr"] <= result["summary"]["haircut_apr"]
    assert result["summary"]["weighted_risk_burden"] > 0
    assert result["summary"]["risk_to_apr_ratio"] > 0
    assert result["summary"]["best_fit_risk_profile"] in {"conservative", "balanced", "aggressive"}
    assert "liquidity_drain" in result["summary"]["fragility_flags"]
