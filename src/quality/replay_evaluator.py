from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.quality.feedback_store import FeedbackStore


def evaluate_replay_window(*, signal_code: str, days: int, store: FeedbackStore) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, days))
    signal_records = store.records_for(signal_code, since=cutoff)
    all_records = store.all_records(since=cutoff)

    sample_size = len(signal_records)
    useful_votes = sum(1 for record in signal_records if record.useful)
    all_useful_votes = sum(1 for record in all_records if record.useful)

    precision = useful_votes / sample_size if sample_size else 0.0
    recall = useful_votes / all_useful_votes if all_useful_votes else 0.0

    return {
        "signal_code": signal_code,
        "days": days,
        "sample_size": sample_size,
        "useful_votes": useful_votes,
        "precision": precision,
        "recall": recall,
    }
