from src.quality.feedback_store import FeedbackStore
from src.quality.replay_evaluator import evaluate_replay_window


def test_replay_evaluator_computes_precision_recall_fields():
    store = FeedbackStore()
    store.record(signal_code="sell_pressure_buildup", useful=True)
    store.record(signal_code="sell_pressure_buildup", useful=False)
    store.record(signal_code="sell_pressure_buildup", useful=True)
    store.record(signal_code="other_signal", useful=True)

    report = evaluate_replay_window(signal_code="sell_pressure_buildup", days=30, store=store)

    assert report["sample_size"] == 3
    assert report["precision"] == 2 / 3
    assert report["recall"] == 2 / 3
