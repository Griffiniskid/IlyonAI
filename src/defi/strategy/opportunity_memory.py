"""In-process opportunity memory keyed by session_id.

Stores the most recent `search_defi_opportunities` items and `allocate_plan`
allocation rows so a follow-up like "execute this pool raydium-amm SPACEX-WSOL"
or "execute the transactions through my wallet" can resolve the chain,
protocol, asset, and amount needed for `build_yield_execution_plan` /
`build_allocation_execution_plan` without re-asking the user.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Any


@dataclass
class OpportunityRecord:
    session_id: str
    items: list[dict[str, Any]] = field(default_factory=list)
    allocations: list[dict[str, Any]] = field(default_factory=list)
    allocation_summary: dict[str, Any] = field(default_factory=dict)
    last_amount_usd: float | None = None
    last_asset_hint: str | None = None
    updated_at: float = field(default_factory=time)


_RECORDS: dict[str, OpportunityRecord] = {}
_LOCK = Lock()


def remember_opportunities(session_id: str, items: list[dict[str, Any]]) -> None:
    if not session_id:
        return
    cleaned = [it for it in (items or []) if isinstance(it, dict)]
    if not cleaned:
        return
    with _LOCK:
        record = _RECORDS.get(session_id) or OpportunityRecord(session_id=session_id)
        record.items = cleaned[:24]
        record.updated_at = time()
        _RECORDS[session_id] = record


def remember_allocation(
    session_id: str,
    allocations: list[dict[str, Any]],
    *,
    total_usd: float | None = None,
    asset_hint: str | None = None,
) -> None:
    if not session_id:
        return
    cleaned = [a for a in (allocations or []) if isinstance(a, dict)]
    if not cleaned:
        return
    with _LOCK:
        record = _RECORDS.get(session_id) or OpportunityRecord(session_id=session_id)
        record.allocations = cleaned[:24]
        if total_usd is not None:
            record.last_amount_usd = float(total_usd)
        if asset_hint:
            record.last_asset_hint = asset_hint
        record.allocation_summary = {
            "rows": len(cleaned),
            "total_usd": record.last_amount_usd,
            "asset_hint": record.last_asset_hint,
        }
        record.updated_at = time()
        _RECORDS[session_id] = record


def recall(session_id: str) -> OpportunityRecord | None:
    if not session_id:
        return None
    with _LOCK:
        return _RECORDS.get(session_id)


def find_opportunity(
    session_id: str,
    *,
    protocol_hint: str | None = None,
    symbol_hint: str | None = None,
    pool_id_hint: str | None = None,
    chain_hint: str | None = None,
    index_hint: int | None = None,
) -> dict[str, Any] | None:
    record = recall(session_id)
    if record is None:
        return None
    candidates = list(record.items)
    if not candidates:
        return None

    if pool_id_hint:
        for it in candidates:
            if str(it.get("pool_id") or "").lower() == pool_id_hint.lower():
                return it

    if index_hint is not None and 1 <= index_hint <= len(candidates):
        return candidates[index_hint - 1]

    def _norm(value: str | None) -> str:
        return (value or "").lower().replace(" ", "").replace("-", "").replace("_", "")

    proto = _norm(protocol_hint)
    sym = _norm(symbol_hint)
    chain = _norm(chain_hint)

    scored: list[tuple[int, dict[str, Any]]] = []
    for it in candidates:
        score = 0
        if proto and proto in _norm(str(it.get("protocol") or "")):
            score += 4
        if sym and sym in _norm(str(it.get("symbol") or "")):
            score += 4
        if chain and chain == _norm(str(it.get("chain") or "")):
            score += 1
        if score:
            scored.append((score, it))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def forget(session_id: str) -> None:
    with _LOCK:
        _RECORDS.pop(session_id, None)


def clear_all_for_test() -> None:
    with _LOCK:
        _RECORDS.clear()
