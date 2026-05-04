"""In-process strategy memory keyed by session_id.

Stores last yield strategy proposal so follow-up prompts ("execute it",
"reinvest the funds", "rebalance it", "compound this") can resolve to the
prior plan without re-asking the user for chain/protocol/asset/amount.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Any


@dataclass
class StrategyRecord:
    session_id: str
    chat_id: str | None
    user_address: str | None
    intent_summary: str
    plan: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    selected_positions: list[dict[str, Any]] = field(default_factory=list)
    reinvest_policy: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)


_RECORDS: dict[str, StrategyRecord] = {}
_LOCK = Lock()


def remember_strategy(record: StrategyRecord) -> None:
    if not record.session_id:
        return
    with _LOCK:
        record.updated_at = time()
        _RECORDS[record.session_id] = record


def recall_strategy(session_id: str) -> StrategyRecord | None:
    if not session_id:
        return None
    with _LOCK:
        return _RECORDS.get(session_id)


def forget_strategy(session_id: str) -> None:
    with _LOCK:
        _RECORDS.pop(session_id, None)


def clear_all_for_test() -> None:
    with _LOCK:
        _RECORDS.clear()
