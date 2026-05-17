"""APScheduler cron registration for the 5-min PositionHealth sweep.

V7-021 stops at registering the job + a placeholder coroutine. V7-022 will
wire the actual snapshot persistence (DB table + repo), and V7-023 will
wire per-protocol value/fee/IL computation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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


async def run_position_health_sweep() -> None:
    """Placeholder for the actual sweep.

    V7-022 will:
      1. Enumerate open positions from the position store.
      2. Compute PositionHealth via per-protocol adapters.
      3. Persist each snapshot via the V7-022 snapshot table.

    For V7-021 we just log so the cron wiring is verifiable end-to-end.
    """
    log.debug("position_health_sweep tick (placeholder — V7-022 will populate)")


def register_position_health_job(
    scheduler: "AsyncIOScheduler",
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
):
    """Register the 5-min PositionHealth sweep on the given scheduler.

    Idempotent: `replace_existing=True` so re-registration on reload doesn't
    raise. `max_instances=1` so a slow sweep can't pile up overlapping runs.

    Returns the registered `Job` so callers can introspect / unschedule it.
    """
    if not _APSCHEDULER_AVAILABLE:
        raise RuntimeError(
            "apscheduler is not installed — cannot register position_health_sweep"
        )
    return scheduler.add_job(
        run_position_health_sweep,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
