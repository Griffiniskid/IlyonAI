from src.analytics.signal_models import BehaviorSignals, EntityHeuristic, SignalFlag


def test_behavior_signals_to_dict_serializes_nested_flags_and_heuristics():
    signals = BehaviorSignals(
        whale_flow_direction="accumulating",
        capital_concentration_score=38.0,
        wallet_stickiness_score=66.0,
        anomaly_flags=[SignalFlag(code="liquidity_drain", severity="high")],
        entity_heuristics=[
            EntityHeuristic(code="deployer_retained_supply", severity="medium", confidence=0.8)
        ],
    )

    payload = signals.to_dict()

    assert payload["whale_flow_direction"] == "accumulating"
    assert payload["anomaly_flags"][0]["code"] == "liquidity_drain"
    assert payload["entity_heuristics"][0]["code"] == "deployer_retained_supply"
