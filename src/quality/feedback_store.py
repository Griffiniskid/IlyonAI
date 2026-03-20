from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class FeedbackRecord:
    signal_code: str
    useful: bool
    created_at: datetime


class FeedbackStore:
    def __init__(self) -> None:
        self._records: list[FeedbackRecord] = []

    def record(self, *, signal_code: str, useful: bool, created_at: datetime | None = None) -> None:
        timestamp = created_at or datetime.now(timezone.utc)
        self._records.append(FeedbackRecord(signal_code=str(signal_code), useful=bool(useful), created_at=timestamp))

    def count(self, signal_code: str) -> int:
        return sum(1 for record in self._records if record.signal_code == signal_code)

    def records_for(self, signal_code: str, *, since: datetime | None = None) -> list[FeedbackRecord]:
        return [
            record
            for record in self._records
            if record.signal_code == signal_code and (since is None or record.created_at >= since)
        ]

    def all_records(self, *, since: datetime | None = None) -> list[FeedbackRecord]:
        if since is None:
            return list(self._records)
        return [record for record in self._records if record.created_at >= since]
