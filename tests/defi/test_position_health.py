"""Pin tests for V7-021 PositionHealth + cron registration."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime

import pytest

from src.defi.position_monitor import (
    DEFAULT_INTERVAL_MINUTES,
    JOB_ID,
    PositionHealth,
    register_position_health_job,
    run_position_health_sweep,
)


def _sample() -> PositionHealth:
    return PositionHealth(
        position_id="uniswap_v3:ethereum:12345",
        chain="ethereum",
        protocol="uniswap_v3",
        current_value_usd=1234.56,
        hodl_value_usd=1300.00,
        fees_collected_usd=12.5,
        fees_uncollected_usd=3.25,
        il_pct=-5.03,  # negative — lost vs HODL
        in_range=True,
        time_in_range_pct=87.4,
        realized_fee_apr=18.2,
        snapshot_at=datetime(2026, 5, 17, 12, 0, 0),
    )


def test_schema_has_eleven_metrics_plus_snapshot_at():
    """11 health metrics + snapshot_at = 12 dataclass fields."""
    names = [f.name for f in fields(PositionHealth)]
    assert len(names) == 12
    expected = {
        "position_id",
        "chain",
        "protocol",
        "current_value_usd",
        "hodl_value_usd",
        "fees_collected_usd",
        "fees_uncollected_usd",
        "il_pct",
        "in_range",
        "time_in_range_pct",
        "realized_fee_apr",
        "snapshot_at",
    }
    assert set(names) == expected


def test_round_trip_to_dict_from_dict_preserves_all_fields():
    original = _sample()
    restored = PositionHealth.from_dict(original.to_dict())
    for f in fields(PositionHealth):
        assert getattr(restored, f.name) == getattr(original, f.name), (
            f"field {f.name} did not round-trip"
        )


def test_to_dict_serializes_snapshot_at_as_iso_string():
    d = _sample().to_dict()
    assert isinstance(d["snapshot_at"], str)
    # parseable back
    assert datetime.fromisoformat(d["snapshot_at"]) == datetime(2026, 5, 17, 12, 0, 0)


def test_snapshot_at_default_is_datetime_instance():
    """Default factory yields a fresh datetime — not None, not a string."""
    ph = PositionHealth(
        position_id="x",
        chain="ethereum",
        protocol="uniswap_v3",
        current_value_usd=1.0,
        hodl_value_usd=1.0,
        fees_collected_usd=0.0,
        fees_uncollected_usd=0.0,
        il_pct=0.0,
        in_range=True,
        time_in_range_pct=100.0,
        realized_fee_apr=0.0,
    )
    assert isinstance(ph.snapshot_at, datetime)


def test_negative_il_pct_allowed():
    """IL is negative when LP underperforms HODL — must not raise / clamp."""
    ph = PositionHealth(
        position_id="x",
        chain="ethereum",
        protocol="uniswap_v3",
        current_value_usd=900.0,
        hodl_value_usd=1000.0,
        fees_collected_usd=0.0,
        fees_uncollected_usd=0.0,
        il_pct=-10.0,
        in_range=False,
        time_in_range_pct=0.0,
        realized_fee_apr=0.0,
    )
    assert ph.il_pct == -10.0
    # round-trip preserves the negative
    assert PositionHealth.from_dict(ph.to_dict()).il_pct == -10.0


def test_from_dict_accepts_datetime_snapshot_at():
    """from_dict should accept both ISO string and raw datetime for snapshot_at."""
    d = _sample().to_dict()
    d["snapshot_at"] = datetime(2026, 5, 17, 13, 0, 0)
    restored = PositionHealth.from_dict(d)
    assert restored.snapshot_at == datetime(2026, 5, 17, 13, 0, 0)


def test_register_position_health_job_registers_correct_id_and_interval():
    apscheduler = pytest.importorskip("apscheduler")
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = AsyncIOScheduler()
    try:
        job = register_position_health_job(scheduler)
        assert job.id == JOB_ID == "position_health_sweep"
        assert isinstance(job.trigger, IntervalTrigger)
        # interval should be exactly 5 minutes (300 s)
        assert job.trigger.interval.total_seconds() == 5 * 60
        assert job.max_instances == 1
        assert job.func is run_position_health_sweep
    finally:
        # AsyncIOScheduler doesn't need to be started to register, but be safe
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_register_position_health_job_custom_interval():
    pytest.importorskip("apscheduler")
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    try:
        job = register_position_health_job(scheduler, interval_minutes=15)
        assert job.trigger.interval.total_seconds() == 15 * 60
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_register_position_health_job_replaces_existing():
    """Idempotent re-registration — replace_existing=True means no DuplicateJobError."""
    pytest.importorskip("apscheduler")
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    try:
        register_position_health_job(scheduler)
        # second call must not raise
        job2 = register_position_health_job(scheduler, interval_minutes=10)
        assert job2.id == JOB_ID
        assert job2.trigger.interval.total_seconds() == 10 * 60
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_default_interval_constant():
    assert DEFAULT_INTERVAL_MINUTES == 5
