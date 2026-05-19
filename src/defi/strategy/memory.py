"""In-process strategy memory keyed by session_id.

Stores last yield strategy proposal so follow-up prompts ("execute it",
"reinvest the funds", "rebalance it", "compound this") can resolve to the
prior plan without re-asking the user for chain/protocol/asset/amount.

RC14: Also caches the last successful `search_defi_opportunities` candidate
universe per session so the ADAPTER_BUILD_FAILED recovery path can populate
`recovery.alternatives` with real executable pools instead of `[]`. The
previous behaviour left the alternatives array empty, forcing the agent to
issue a fresh search (G04 t3) instead of substituting from the universe it
had already ranked.
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
        _SEARCH_UNIVERSE.clear()


# ── RC14: search-universe cache for alt-pool recovery ────────────────────────
#
# Keyed by session_id. Stores the list of OpportunityCandidate dicts from the
# last successful search_defi_opportunities call so build_yield_execution_plan
# can substitute an alternative pool from the SAME ranked universe when an
# adapter build fails. Never auto-routes — only feeds recovery.alternatives so
# the user picks (spec §6f hard rule preserved).
_SEARCH_UNIVERSE: dict[str, list[dict[str, Any]]] = {}


def remember_search_universe(session_id: str, candidates: list[dict[str, Any]]) -> None:
    """Cache the ranked candidate list from a successful search call.

    Callers should pass the `primary_candidates` payload (each entry must
    carry at least `protocol_slug`, `chain`, `symbol`, `pool_id`, `apy`,
    `tvl_usd`, `executable`). Capped at 32 entries to bound memory.
    """
    if not session_id or not candidates:
        return
    capped = list(candidates)[:32]
    with _LOCK:
        _SEARCH_UNIVERSE[session_id] = capped


def recall_search_universe(session_id: str) -> list[dict[str, Any]]:
    """Return the cached search universe for a session, or [] if none."""
    if not session_id:
        return []
    with _LOCK:
        return list(_SEARCH_UNIVERSE.get(session_id, []))


def pick_alt_pools(
    session_id: str,
    *,
    failed_pool_id: str | None = None,
    failed_protocol: str | None = None,
    chain: str | None = None,
    asset: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Surface up to `limit` ranked alternatives from the cached universe.

    Filters:
      - Drop the just-failed pool (matched by pool_id OR protocol_slug).
      - Prefer same-chain candidates.
      - Prefer same-asset (symbol) candidates.
      - Prefer executable candidates so the recovery suggests something the
        user can actually deposit into without another adapter miss.

    The returned dicts carry the fields the frontend recovery card needs
    (protocol, chain, symbol, pool_id, apy, tvl_usd, risk_level,
    executable, adapter_id, source_urls).
    """
    universe = recall_search_universe(session_id)
    if not universe:
        return []

    failed_pid = (failed_pool_id or "").strip().lower()
    failed_proto = (failed_protocol or "").strip().lower()
    target_chain = (chain or "").strip().lower()
    target_asset = (asset or "").strip().upper()

    def _key(item: dict[str, Any]) -> tuple[int, int, int, float]:
        # Higher tuples sort earlier (we'll negate apy for descending).
        same_chain = 1 if target_chain and str(item.get("chain") or "").lower() == target_chain else 0
        sym_up = str(item.get("symbol") or "").upper()
        same_asset = 1 if target_asset and (
            target_asset == sym_up or target_asset in sym_up.split("-")
        ) else 0
        executable = 1 if item.get("executable") else 0
        try:
            apy = float(item.get("apy") or 0.0)
        except (TypeError, ValueError):
            apy = 0.0
        return (same_chain, same_asset, executable, apy)

    survivors: list[dict[str, Any]] = []
    for item in universe:
        pid = str(item.get("pool_id") or "").lower()
        proto = str(item.get("protocol_slug") or item.get("protocol") or "").lower()
        if failed_pid and pid and pid == failed_pid:
            continue
        # Drop a same-protocol+same-chain candidate that's almost certainly
        # the same pool under a different pool_id; alt-pool recovery means
        # "different route", not "same protocol, retry".
        if (
            failed_proto
            and proto
            and proto == failed_proto
            and target_chain
            and str(item.get("chain") or "").lower() == target_chain
        ):
            continue
        survivors.append(item)

    survivors.sort(key=_key, reverse=True)
    return survivors[:max(1, int(limit))]
