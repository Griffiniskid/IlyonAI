from src.defi.scoring.deterministic import DeterministicScorer


def test_risk_to_apr_ratio_rises_when_risk_burden_increases_at_same_apr():
    scorer = DeterministicScorer()
    base_candidate = {"product_type": "stable_lp", "apy": 10.0, "apy_base": 8.0, "apy_reward": 2.0, "tvl_usd": 5_000_000}
    safer = scorer.score(kind="pool", candidate=base_candidate, context={"protocol_safety": 88, "behavior": {}, "history": {}, "docs": {"available": True}})
    riskier = scorer.score(
        kind="pool",
        candidate=base_candidate,
        context={
            "protocol_safety": 60,
            "behavior": {"anomaly_flags": [{"code": "liquidity_drain", "severity": "high"}]},
            "history": {},
            "docs": {},
        },
    )

    assert riskier["summary"]["risk_to_apr_ratio"] > safer["summary"]["risk_to_apr_ratio"]
