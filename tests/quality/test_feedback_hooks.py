from src.analytics.behavior_signals import BehaviorSignalBuilder
from src.quality.feedback_store import FeedbackStore


def test_feedback_hook_persists_usefulness_vote():
    store = FeedbackStore()

    store.record(signal_code="sell_pressure_buildup", useful=True)

    assert store.count("sell_pressure_buildup") == 1


def test_behavior_signal_builder_records_votes_per_signal_code():
    store = FeedbackStore()
    builder = BehaviorSignalBuilder(feedback_store=store)

    builder.build(
        anomalies=[
            {"code": "sell_pressure_buildup", "severity": "high"},
            {"code": "liquidity_drain", "severity": "medium"},
        ],
        heuristics=[{"code": "possible_insider_cluster", "severity": "low"}],
        usefulness_votes={
            "sell_pressure_buildup": True,
            "possible_insider_cluster": False,
        },
    )

    assert store.count("sell_pressure_buildup") == 1
    assert store.count("possible_insider_cluster") == 1
    assert store.count("liquidity_drain") == 0
