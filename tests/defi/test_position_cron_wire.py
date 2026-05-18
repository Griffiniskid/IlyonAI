"""Pin test for V7-022/V7-023 cron wiring.

`src/defi/position_monitor/cron.py::run_position_health_sweep` is the
integration point that:

  - enumerates open user_positions rows,
  - persists a PositionHealth snapshot per row via insert_snapshot,
  - runs the four detectors,
  - persists an insert_alert row per detector emission.

These tests mock the session + the position enumerator + the snapshot
repo + the detectors so no real DB is touched. They lock in:

  1. one snapshot per enumerated open position,
  2. one alert per detector emission,
  3. zero alerts when every detector returns None,
  4. the session factory is invoked exactly once per sweep (so we don't
     leak transactions if a row blows up).
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.defi.position_monitor import cron as cron_mod


class _FakeSession:
    """Async-context-manager-shaped session that records nothing — the
    repo calls themselves are patched at module level, so the session
    only needs to be a placeholder that satisfies `async with`.
    """

    def __init__(self) -> None:
        self.commits = 0

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


def _make_session_factory() -> tuple[Any, list[_FakeSession]]:
    """Returns (factory, list-of-sessions-yielded) so tests can introspect."""
    yielded: list[_FakeSession] = []

    def _factory() -> _FakeSession:
        s = _FakeSession()
        yielded.append(s)
        return s

    return _factory, yielded


def _two_open_positions() -> list[dict[str, Any]]:
    return [
        {
            "position_id": "pos-alpha",
            "chain_id": 1,
            "protocol": "uniswap-v3",
            "status": "open",
        },
        {
            "position_id": "pos-beta",
            "chain_id": 42161,
            "protocol": "balancer-v2",
            "status": "open",
        },
    ]


def test_sweep_inserts_one_snapshot_per_open_position(monkeypatch):
    """Two open positions → exactly two insert_snapshot calls."""
    snap_calls: list[tuple[str, dict]] = []
    alert_calls: list[tuple[str, str, dict]] = []

    async def _fake_insert_snapshot(session, position_id, payload):
        snap_calls.append((position_id, payload))
        return len(snap_calls)

    async def _fake_get_latest(session, position_id, limit=1):
        return []

    async def _fake_insert_alert(session, position_id, alert_type, payload):
        alert_calls.append((position_id, alert_type, payload))
        return len(alert_calls)

    monkeypatch.setattr(cron_mod, "insert_snapshot", _fake_insert_snapshot)
    monkeypatch.setattr(cron_mod, "get_latest_snapshots", _fake_get_latest)
    monkeypatch.setattr(cron_mod, "insert_alert", _fake_insert_alert)

    async def _finder(session):
        return _two_open_positions()

    factory, yielded = _make_session_factory()

    result = asyncio.run(
        cron_mod.run_position_health_sweep(
            factory,
            find_user_positions=_finder,
        )
    )

    assert result["positions"] == 2
    assert result["snapshots"] == 2
    assert len(snap_calls) == 2
    assert {pid for pid, _ in snap_calls} == {"pos-alpha", "pos-beta"}
    # session factory invoked exactly once for the whole sweep.
    assert len(yielded) == 1
    # no detectors fired (history was empty + no tvl/gas data) → no alerts.
    assert alert_calls == []
    assert result["alerts"] == 0


def test_sweep_writes_alert_when_detector_fires(monkeypatch):
    """One position whose detector fires → exactly one insert_alert call."""
    snap_calls: list[tuple[str, dict]] = []
    alert_calls: list[tuple[str, str, dict]] = []

    async def _fake_insert_snapshot(session, position_id, payload):
        snap_calls.append((position_id, payload))
        return len(snap_calls)

    async def _fake_get_latest(session, position_id, limit=1):
        # Doesn't matter what we return — the detector below ignores it.
        return []

    async def _fake_insert_alert(session, position_id, alert_type, payload):
        alert_calls.append((position_id, alert_type, payload))
        return len(alert_calls)

    monkeypatch.setattr(cron_mod, "insert_snapshot", _fake_insert_snapshot)
    monkeypatch.setattr(cron_mod, "get_latest_snapshots", _fake_get_latest)
    monkeypatch.setattr(cron_mod, "insert_alert", _fake_insert_alert)

    # Force detect_out_of_range to fire for every call so we can assert
    # the cron path persists exactly one alert per emission.
    def _always_fire_out_of_range(history):
        pid = "<unknown>"
        for snap in history:
            if isinstance(snap, dict) and snap.get("position_id"):
                pid = snap["position_id"]
        return {
            "alert_type": "OUT_OF_RANGE",
            "severity": "warning",
            "message": "forced",
            "payload": {"position_id": pid, "forced": True},
        }

    def _never_fire(*args, **kwargs):
        return None

    monkeypatch.setattr(cron_mod, "detect_out_of_range", _always_fire_out_of_range)
    monkeypatch.setattr(cron_mod, "detect_fee_apr_drop", _never_fire)
    monkeypatch.setattr(cron_mod, "detect_tvl_exodus", _never_fire)
    monkeypatch.setattr(cron_mod, "detect_gas_favorable", _never_fire)

    async def _finder(session):
        return [_two_open_positions()[0]]  # single position

    factory, _ = _make_session_factory()

    result = asyncio.run(
        cron_mod.run_position_health_sweep(
            factory,
            find_user_positions=_finder,
        )
    )

    assert result["positions"] == 1
    assert result["snapshots"] == 1
    assert result["alerts"] == 1
    assert len(alert_calls) == 1
    pid, atype, payload = alert_calls[0]
    assert pid == "pos-alpha"
    assert atype == "OUT_OF_RANGE"
    assert payload.get("forced") is True


def test_sweep_writes_no_alert_when_all_detectors_return_none(monkeypatch):
    """When every detector returns None, no insert_alert calls are made."""
    snap_calls: list[tuple[str, dict]] = []
    alert_calls: list[tuple[str, str, dict]] = []

    async def _fake_insert_snapshot(session, position_id, payload):
        snap_calls.append((position_id, payload))

    async def _fake_get_latest(session, position_id, limit=1):
        return []

    async def _fake_insert_alert(session, position_id, alert_type, payload):
        alert_calls.append((position_id, alert_type, payload))

    monkeypatch.setattr(cron_mod, "insert_snapshot", _fake_insert_snapshot)
    monkeypatch.setattr(cron_mod, "get_latest_snapshots", _fake_get_latest)
    monkeypatch.setattr(cron_mod, "insert_alert", _fake_insert_alert)

    monkeypatch.setattr(cron_mod, "detect_out_of_range", lambda *a, **kw: None)
    monkeypatch.setattr(cron_mod, "detect_fee_apr_drop", lambda *a, **kw: None)
    monkeypatch.setattr(cron_mod, "detect_tvl_exodus", lambda *a, **kw: None)
    monkeypatch.setattr(cron_mod, "detect_gas_favorable", lambda *a, **kw: None)

    async def _finder(session):
        return _two_open_positions()

    factory, _ = _make_session_factory()

    result = asyncio.run(
        cron_mod.run_position_health_sweep(
            factory,
            find_user_positions=_finder,
        )
    )

    assert result["positions"] == 2
    assert result["snapshots"] == 2
    assert result["alerts"] == 0
    assert alert_calls == []


def test_sweep_returns_zero_when_no_open_positions(monkeypatch):
    """Empty position list → no snapshot or alert calls; counters all zero."""
    snap_calls: list[Any] = []
    alert_calls: list[Any] = []

    async def _fake_insert_snapshot(session, position_id, payload):
        snap_calls.append(1)

    async def _fake_get_latest(session, position_id, limit=1):
        return []

    async def _fake_insert_alert(session, position_id, alert_type, payload):
        alert_calls.append(1)

    monkeypatch.setattr(cron_mod, "insert_snapshot", _fake_insert_snapshot)
    monkeypatch.setattr(cron_mod, "get_latest_snapshots", _fake_get_latest)
    monkeypatch.setattr(cron_mod, "insert_alert", _fake_insert_alert)

    async def _finder(session):
        return []

    factory, _ = _make_session_factory()

    result = asyncio.run(
        cron_mod.run_position_health_sweep(
            factory,
            find_user_positions=_finder,
        )
    )

    assert result == {"positions": 0, "snapshots": 0, "alerts": 0}
    assert snap_calls == []
    assert alert_calls == []
