from src.analytics.behavior_signals import BehaviorSignalBuilder


def test_behavior_signals_emit_direction_concentration_and_stickiness():
    builder = BehaviorSignalBuilder()

    result = builder.build(
        whale_summary={
            "net_flow_usd": 120000,
            "buy_count": 5,
            "sell_count": 1,
            "repeat_wallet_share": 0.6,
        },
        concentration={"top_wallet_share": 0.38},
        anomalies=[{"code": "liquidity_drain", "severity": "high"}],
    )

    assert result.whale_flow_direction == "accumulating"
    assert result.capital_concentration_score == 38.0
    assert result.wallet_stickiness_score == 60.0
    assert result.anomaly_flags[0].code == "liquidity_drain"


def test_behavior_signals_include_entity_heuristics_from_wallet_forensics():
    builder = BehaviorSignalBuilder()

    result = builder.build(
        whale_summary={"net_flow_usd": -60000, "buy_count": 1, "sell_count": 4},
        concentration={"top_wallet_share": 0.12},
        heuristics=[
            {"code": "possible_insider_cluster", "severity": "medium", "confidence": 0.7}
        ],
    )

    assert result.whale_flow_direction == "distributing"
    assert result.entity_heuristics[0].code == "possible_insider_cluster"
