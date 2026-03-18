from src.defi.scoring.deterministic import DeterministicScorer


def test_vault_scoring_assigns_best_fit_profile_and_fragility_flags():
    scorer = DeterministicScorer()
    result = scorer.score(
        kind="vault",
        candidate={
            "product_type": "vault",
            "apy": 14.0,
            "apy_base": 10.0,
            "apy_reward": 4.0,
            "tvl_usd": 3_000_000,
        },
        context={
            "protocol_safety": 70,
            "behavior": {"anomaly_flags": [{"code": "strategy_turnover", "severity": "medium"}]},
            "history": {"available": True, "apy_persistence_score": 60},
            "docs": {"available": True},
        },
    )

    assert result["summary"]["best_fit_risk_profile"] in {"conservative", "balanced", "aggressive"}
    assert "strategy_turnover" in result["summary"]["fragility_flags"]
