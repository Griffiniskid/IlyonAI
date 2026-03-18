from src.defi.scoring.deterministic import DeterministicScorer


def test_missing_evidence_never_increases_confidence():
    scorer = DeterministicScorer()
    rich_context = {
        "protocol_safety": 80,
        "behavior": {},
        "history": {"available": True, "apy_persistence_score": 70},
        "docs": {"available": True, "freshness_hours": 2},
        "dependencies": [{"dependency_type": "protocol", "risk_score": 25}],
    }
    sparse_context = {"protocol_safety": 80, "behavior": {}, "history": {}, "docs": {}, "dependencies": []}
    candidate = {"product_type": "stable_lp", "apy": 7.0, "apy_base": 6.0, "apy_reward": 1.0, "tvl_usd": 3_000_000}

    rich = scorer.score(kind="pool", candidate=candidate, context=rich_context)
    sparse = scorer.score(kind="pool", candidate=candidate, context=sparse_context)

    assert sparse["confidence"]["score"] <= rich["confidence"]["score"]


def test_higher_protocol_safety_keeps_weighted_risk_burden_from_rising():
    scorer = DeterministicScorer()
    candidate = {"product_type": "stable_lp", "apy": 9.0, "apy_base": 7.0, "apy_reward": 2.0, "tvl_usd": 4_000_000}
    burdens = []
    for protocol_safety in [55, 65, 75, 85]:
        result = scorer.score(kind="pool", candidate=candidate, context={"protocol_safety": protocol_safety, "behavior": {}, "history": {}, "docs": {}})
        burdens.append(result["summary"]["weighted_risk_burden"])

    assert burdens == sorted(burdens, reverse=True)
