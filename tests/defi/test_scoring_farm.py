from src.defi.scoring.deterministic import DeterministicScorer


def test_farm_behavior_signals_reduce_deterministic_score():
    scorer = DeterministicScorer()
    base_candidate = {
        "product_type": "incentivized_crypto_crypto_lp",
        "apy": 48.0,
        "apy_base": 8.0,
        "apy_reward": 40.0,
        "tvl_usd": 900_000,
        "volume_usd_1d": 160_000,
        "il_risk": "yes",
    }
    calm = scorer.score(kind="yield", candidate=base_candidate, context={"protocol_safety": 62, "behavior": {}, "history": {}, "docs": {}})
    stressed = scorer.score(
        kind="yield",
        candidate=base_candidate,
        context={
            "protocol_safety": 62,
            "behavior": {
                "capital_concentration_score": 88,
                "anomaly_flags": [{"code": "reward_instability", "severity": "critical"}],
            },
            "history": {},
            "docs": {},
        },
    )

    assert stressed["summary"]["haircut_apr"] < calm["summary"]["haircut_apr"]
    assert stressed["summary"]["weighted_risk_burden"] > calm["summary"]["weighted_risk_burden"]
    assert stressed["summary"]["kill_switches"]
    assert "reward_instability" in stressed["summary"]["fragility_flags"]
