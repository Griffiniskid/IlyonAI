from src.defi.scoring.deterministic import DeterministicScorer


def test_lending_supply_scoring_emits_decision_bundle_fields():
    scorer = DeterministicScorer()
    result = scorer.score(
        kind="lending",
        candidate={
            "product_type": "lending_supply_like",
            "apy": 5.2,
            "apy_supply": 5.2,
            "apy_borrow": 8.5,
            "utilization_pct": 54,
            "tvl_usd": 25_000_000,
        },
        context={"protocol_safety": 84, "behavior": {}, "history": {}, "docs": {"available": True}},
    )

    summary = result["summary"]
    assert summary["gross_apr"] == 5.2
    assert summary["haircut_apr"] <= summary["gross_apr"]
    assert summary["net_expected_apr"] <= summary["haircut_apr"]
    assert summary["risk_to_apr_ratio"] >= 0
    assert isinstance(summary["confidence_reasoning"], list)
