"""APScheduler cron registration for the 5-min PositionHealth sweep.

V7-021 registered the job + a placeholder coroutine. V7-022/023 now wire
the real sweep:

    1. Enumerate every currently-open user_positions row.
    2. Compute a PositionHealth snapshot per position. For protocols
       without live valuation data yet, we use placeholder/zeroed
       fields so the snapshot row + downstream detectors still flow
       end-to-end. As per-protocol value/fee/IL adapters land, this
       function becomes the integration point.
    3. Persist the snapshot via `insert_snapshot` (V7-022 table).
    4. Pull the trailing 24-snapshot window via `get_latest_snapshots`
       and run all four detectors from `detectors.py`.
    5. For each detector emission, persist a `position_alerts` row via
       `insert_alert` (V7-023 table).

The job accepts an injected session factory (`session_factory`) and an
injected position-enumeration callable (`find_user_positions`) so unit
tests can swap both for mocks without touching a real DB.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING

from src.defi.position_monitor.detectors import (
    detect_fee_apr_drop,
    detect_gas_favorable,
    detect_out_of_range,
    detect_tvl_exodus,
)
from src.defi.position_monitor.position_health import PositionHealth
from src.storage.repositories.position_alert import insert_alert
from src.storage.repositories.position_snapshot import (
    get_latest_snapshots,
    insert_snapshot,
)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    _APSCHEDULER_AVAILABLE = True
except ImportError:  # pragma: no cover - apscheduler is in requirements.txt
    AsyncIOScheduler = None  # type: ignore[assignment,misc]
    IntervalTrigger = None  # type: ignore[assignment,misc]
    _APSCHEDULER_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover
    from apscheduler.schedulers.asyncio import AsyncIOScheduler as _SchedulerT

log = logging.getLogger(__name__)

JOB_ID = "position_health_sweep"
DEFAULT_INTERVAL_MINUTES = 5

# Chain-id → slug map used to translate the integer `chain_id` stored on
# `user_positions` into the chain slug that `detect_gas_favorable` and
# `PositionHealth.chain` expect. Only EVM majors that ship in the
# detector's `_EVM_CHAINS` set are listed; anything else falls back to
# the stringified id (effectively disabling the gas detector for that
# row, which is the safe default).
_CHAIN_ID_TO_SLUG: dict[int, str] = {
    1: "ethereum",
    10: "optimism",
    56: "bsc",
    100: "gnosis",
    137: "polygon",
    250: "fantom",
    8453: "base",
    42161: "arbitrum",
    43114: "avalanche",
    59144: "linea",
    81457: "blast",
    34443: "mode",
    1088: "metis",
    5000: "mantle",
    324: "zksync",
    42220: "celo",
    534352: "scroll",
}


SessionFactory = Callable[[], Any]
FindPositions = Callable[[Any], Awaitable[list[dict[str, Any]]]]


async def _default_find_user_positions(session: Any) -> list[dict[str, Any]]:
    """Enumerate every `user_positions` row where status='open'.

    Unlike `src.defi.position_store.find_open_positions` (which filters
    by a single wallet), the cron sweep needs the global open set. We
    issue a raw SELECT here rather than extend the store helper because
    this is the only caller that wants the unfiltered view.
    """
    from sqlalchemy import text

    sql = text("SELECT * FROM user_positions WHERE status = 'open'")
    result = await session.execute(sql)
    rows = result.mappings().all() if hasattr(result, "mappings") else list(result)
    return [dict(r) for r in rows]


def _build_placeholder_health(row: dict[str, Any]) -> PositionHealth:
    """Build a zero-valued PositionHealth for rows without a live adapter.

    Per-protocol valuation lands incrementally (V7-026+). Until then we
    still want a snapshot row per tick so detectors have something to
    operate on and the storage path is exercised in production.
    """
    chain_id = row.get("chain_id")
    chain_slug = _CHAIN_ID_TO_SLUG.get(int(chain_id)) if chain_id is not None else None
    if not chain_slug:
        chain_slug = str(chain_id) if chain_id is not None else "unknown"

    return PositionHealth(
        position_id=str(row.get("position_id") or ""),
        chain=chain_slug,
        protocol=str(row.get("protocol") or "unknown"),
        current_value_usd=0.0,
        hodl_value_usd=0.0,
        fees_collected_usd=0.0,
        fees_uncollected_usd=0.0,
        il_pct=0.0,
        in_range=True,
        time_in_range_pct=100.0,
        realized_fee_apr=0.0,
        snapshot_at=datetime.utcnow(),
    )


def _snapshots_for_detectors(rows: list[dict[str, Any]]) -> list[dict]:
    """Flatten get_latest_snapshots() output into detector-ready dicts.

    Detectors expect the PositionHealth payload shape directly (keys
    like `in_range`, `realized_fee_apr`). The repo returns rows wrapping
    that payload under `payload`. We unwrap, attach `snapshot_at`, and
    return oldest-first (detectors walk chronologically).
    """
    out: list[dict] = []
    for row in rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        merged = dict(payload)
        if "snapshot_at" not in merged and row.get("snapshot_at") is not None:
            merged["snapshot_at"] = row["snapshot_at"]
        if "position_id" not in merged and row.get("position_id") is not None:
            merged["position_id"] = row["position_id"]
        out.append(merged)
    # repo returns newest-first; detectors expect oldest-first.
    out.reverse()
    return out


async def _sweep_one(
    session: Any,
    row: dict[str, Any],
    *,
    health_builder: Callable[[dict[str, Any]], PositionHealth],
) -> tuple[int, int]:
    """Snapshot one position and fire its detectors. Returns (snaps, alerts)."""
    position_id = str(row.get("position_id") or "")
    if not position_id:
        return (0, 0)

    health = health_builder(row)
    payload = health.to_dict()
    await insert_snapshot(session, position_id, payload)

    history_rows = await get_latest_snapshots(session, position_id, limit=24)
    history = _snapshots_for_detectors(history_rows)

    alerts_written = 0

    out_of_range = detect_out_of_range(history)
    if out_of_range:
        await insert_alert(
            session,
            position_id,
            out_of_range["alert_type"],
            out_of_range.get("payload") or {},
        )
        alerts_written += 1

    apr_drop = detect_fee_apr_drop(history)
    if apr_drop:
        await insert_alert(
            session,
            position_id,
            apr_drop["alert_type"],
            apr_drop.get("payload") or {},
        )
        alerts_written += 1

    # TVL exodus + gas-favorable are pool/chain-scoped, not snapshot-scoped.
    # The cron sweep doesn't yet pull live TVL history or gas oracles per
    # iteration — those data sources land in a follow-up V7 batch. We invoke
    # the detectors here with the data we have (empty TVL history, no gas),
    # which makes them no-op gracefully and keeps the wiring honest: the
    # moment a caller passes real data the alerts will start firing.
    tvl_history = row.get("tvl_history") if isinstance(row, dict) else None
    if isinstance(tvl_history, list):
        tvl_alert = detect_tvl_exodus(tvl_history)
        if tvl_alert:
            await insert_alert(
                session,
                position_id,
                tvl_alert["alert_type"],
                tvl_alert.get("payload") or {},
            )
            alerts_written += 1

    current_gas = row.get("current_gas_gwei") if isinstance(row, dict) else None
    if current_gas is not None:
        gas_alert = detect_gas_favorable(health.chain, float(current_gas))
        if gas_alert:
            await insert_alert(
                session,
                position_id,
                gas_alert["alert_type"],
                gas_alert.get("payload") or {},
            )
            alerts_written += 1

    return (1, alerts_written)


async def run_position_health_sweep(
    session_factory: Optional[SessionFactory] = None,
    *,
    find_user_positions: Optional[FindPositions] = None,
    health_builder: Optional[Callable[[dict[str, Any]], PositionHealth]] = None,
) -> dict[str, int]:
    """Run one full health-sweep pass and return counters.

    Args:
        session_factory: zero-arg callable that returns an `async with`-
            capable session (SQLAlchemy's `async_sessionmaker()` matches
            this shape). When None we resolve `get_database().async_session`
            lazily so the default scheduler-driven invocation still works.
        find_user_positions: async callable that, given a session, returns
            the list of open-position rows to sweep. Defaults to the
            global `SELECT * FROM user_positions WHERE status='open'`.
        health_builder: pure function that maps one position row to a
            `PositionHealth` dataclass. Defaults to a zero-valued
            placeholder until per-protocol adapters land.

    Returns a `{"positions": int, "snapshots": int, "alerts": int}` dict
    so callers (tests, observability) can assert on the work done.
    """
    if session_factory is None:
        try:
            from src.storage.database import get_database  # local import: avoid cycle

            db = get_database()
            session_factory = db.async_session
        except Exception as exc:  # pragma: no cover - environmental
            log.warning("position_health_sweep: no session_factory available (%s)", exc)
            return {"positions": 0, "snapshots": 0, "alerts": 0}

    finder = find_user_positions or _default_find_user_positions
    builder = health_builder or _build_placeholder_health

    snapshots_written = 0
    alerts_written = 0
    positions_seen = 0

    async with session_factory() as session:
        try:
            rows = await finder(session)
        except Exception as exc:
            log.warning("position_health_sweep: enumeration failed (%s)", exc)
            return {"positions": 0, "snapshots": 0, "alerts": 0}

        for row in rows:
            positions_seen += 1
            try:
                snaps, alerts = await _sweep_one(session, row, health_builder=builder)
                snapshots_written += snaps
                alerts_written += alerts
            except Exception as exc:
                log.warning(
                    "position_health_sweep: row failed (position_id=%s): %s",
                    row.get("position_id") if isinstance(row, dict) else "<?>",
                    exc,
                )

        commit = getattr(session, "commit", None)
        if callable(commit):
            try:
                await commit()
            except Exception as exc:  # pragma: no cover - commit is best-effort
                log.debug("position_health_sweep: commit raised (%s)", exc)

    log.info(
        "position_health_sweep complete: positions=%d snapshots=%d alerts=%d",
        positions_seen,
        snapshots_written,
        alerts_written,
    )
    return {
        "positions": positions_seen,
        "snapshots": snapshots_written,
        "alerts": alerts_written,
    }


def register_position_health_job(
    scheduler: "AsyncIOScheduler",
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    *,
    session_factory: Optional[SessionFactory] = None,
    find_user_positions: Optional[FindPositions] = None,
    health_builder: Optional[Callable[[dict[str, Any]], PositionHealth]] = None,
):
    """Register the 5-min PositionHealth sweep on the given scheduler.

    Idempotent: `replace_existing=True` so re-registration on reload doesn't
    raise. `max_instances=1` so a slow sweep can't pile up overlapping runs.

    Optional injectables (`session_factory`, `find_user_positions`,
    `health_builder`) are forwarded into the scheduled coroutine via a
    closure so the caller in `src/main.py` can wire production DB access
    while tests use mocks.

    Returns the registered `Job` so callers can introspect / unschedule it.
    """
    if not _APSCHEDULER_AVAILABLE:
        raise RuntimeError(
            "apscheduler is not installed — cannot register position_health_sweep"
        )

    # When no injectables are provided we register the bare coroutine so
    # introspection (`job.func is run_position_health_sweep`) and the
    # default lazy-DB path both keep working. Only wrap in a closure when
    # the caller actually has overrides to forward — that's the prod path
    # in `src/main.py` where a real session_factory + per-protocol
    # health_builder will eventually land.
    if session_factory is None and find_user_positions is None and health_builder is None:
        job_callable: Any = run_position_health_sweep
    else:
        async def _job() -> None:
            await run_position_health_sweep(
                session_factory,
                find_user_positions=find_user_positions,
                health_builder=health_builder,
            )

        job_callable = _job

    return scheduler.add_job(
        job_callable,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
