"""Pin test for V7-023 (agent_012): position_alerts spec columns + repo.

Verifies:
  1. Migration module loads cleanly and exposes the agent_012 ->
     agent_011 -> agent_010 -> agent_009 revision chain (with
     alembic.op stubbed so the test runs even when alembic isn't
     installed in the unit env). upgrade() + downgrade() smoke-call.
  2. `insert_alert` round-trips `(position_id, alert_type, payload)`
     into a captured INSERT statement and returns the autoincrement
     PK (probed via the SQLite RETURNING fallback).
  3. `get_open_alerts` filters on `dismissed_at IS NULL` — insert 2,
     all 2 returned; dismiss one, only 1 returned.
  4. `dismiss_alert` issues an UPDATE that sets dismissed_at on the
     target alert_id.

The FakeSession mirrors V7-004's pattern (records executed
(sql, params) tuples; returns a mappings()-compatible Result). It also
supports a tiny in-memory backing store so we can simulate the
insert -> select -> dismiss -> select round trip without standing up
a real DB.

Spec ref: IlyonAi_Development_Plan_v2.md V7-023.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest


# ─── Test fixture: a minimal in-memory FakeSession ────────────────────────


class _Result:
    """Mimics SQLAlchemy `Result` for the surface the repo uses."""

    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict]:
        return list(self._rows)

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Async session double matching V7-004's FakeSession shape.

    Records every (sql, params) tuple in `self.statements` so tests can
    assert on the SQL text and the bound params, AND maintains a tiny
    in-memory store so insert -> get -> dismiss -> get round-trips
    work end to end.
    """

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict | None]] = []
        # Backing store: list of dicts keyed by alert_id.
        self._rows: list[dict] = []
        self._next_id = 1
        # Match the dialect probe in `insert_alert` so the SQLite
        # branch (no RETURNING) is exercised.
        self.bind = type(
            "B",
            (),
            {"dialect": type("D", (), {"name": "sqlite"})()},
        )()

    async def execute(self, statement, params=None, *a, **kw) -> _Result:
        sql = str(statement)
        self.statements.append((sql, params))
        sql_upper = sql.upper()

        if "INSERT INTO POSITION_ALERTS" in sql_upper:
            assert params is not None
            row = {
                "alert_id": self._next_id,
                "id": self._next_id,
                "position_id": params["position_id"],
                "alert_type": params["alert_type"],
                "fired_at": "2026-05-17T00:00:00Z",
                "payload": params["payload"],
                "dismissed_at": None,
            }
            self._rows.append(row)
            self._next_id += 1
            return _Result([])

        if "LAST_INSERT_ROWID" in sql_upper:
            # The SQLite fallback path in insert_alert.
            last_id = self._rows[-1]["alert_id"] if self._rows else 0
            return _Result([{"id": last_id}])

        if "SELECT" in sql_upper and "POSITION_ALERTS" in sql_upper:
            assert params is not None
            pid = params["position_id"]
            rows = [
                {
                    "id": r["alert_id"],
                    "position_id": r["position_id"],
                    "alert_type": r["alert_type"],
                    "fired_at": r["fired_at"],
                    "payload": r["payload"],
                    "dismissed_at": r["dismissed_at"],
                }
                for r in self._rows
                if r["position_id"] == pid and r["dismissed_at"] is None
            ]
            return _Result(rows)

        if "UPDATE POSITION_ALERTS" in sql_upper:
            assert params is not None
            aid = int(params["alert_id"])
            for r in self._rows:
                if r["alert_id"] == aid:
                    r["dismissed_at"] = "2026-05-17T00:00:01Z"
            return _Result([])

        return _Result([])


# ─── Migration import test ────────────────────────────────────────────────


def test_migration_module_imports_cleanly():
    """agent_012 parses, declares the right revision chain, and the
    upgrade/downgrade bodies smoke-call against a stubbed `alembic.op`.

    Mirrors V7-004's loader (spec_from_file_location + alembic stub)
    so the test runs without alembic installed.
    """
    import importlib.util
    import sys
    import types
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    mig_path = (
        repo_root
        / "migrations"
        / "versions"
        / "20260517_agent_012_position_alerts.py"
    )
    assert mig_path.exists(), f"migration file missing: {mig_path}"

    if "alembic" not in sys.modules:
        alembic_stub = types.ModuleType("alembic")
        op_stub = types.SimpleNamespace(
            add_column=lambda *a, **kw: None,
            drop_column=lambda *a, **kw: None,
            create_index=lambda *a, **kw: None,
            drop_index=lambda *a, **kw: None,
            get_bind=lambda: None,
        )
        alembic_stub.op = op_stub
        sys.modules["alembic"] = alembic_stub
    else:
        # Backfill any methods the existing stub may have skipped so
        # subsequent migration tests don't bleed into ours.
        op = sys.modules["alembic"].op
        for name in (
            "add_column",
            "drop_column",
            "create_index",
            "drop_index",
        ):
            if not hasattr(op, name):
                setattr(op, name, lambda *a, **kw: None)
        if not hasattr(op, "get_bind"):
            op.get_bind = lambda: None  # type: ignore[attr-defined]

    spec = importlib.util.spec_from_file_location(
        "agent_012_position_alerts", str(mig_path)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "agent_012"
    assert mod.down_revision == "agent_011"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    # Smoke-call: verifies no NameError / typo in column definitions.
    mod.upgrade()
    mod.downgrade()


# ─── Repo round-trip tests ────────────────────────────────────────────────


def test_insert_alert_round_trips_payload():
    """insert_alert binds (position_id, alert_type, payload) and
    returns the autoincrement PK via the SQLite RETURNING fallback."""
    from src.storage.repositories.position_alert import insert_alert

    session = _FakeSession()

    alert_id = asyncio.run(
        insert_alert(
            session,
            position_id="pos-001",
            alert_type="out_of_range",
            payload={"side": "upper", "ticks": 42},
        )
    )

    assert alert_id == 1
    # First call = INSERT, second = SELECT last_insert_rowid().
    assert len(session.statements) == 2
    insert_sql, insert_params = session.statements[0]
    assert "INSERT INTO position_alerts" in insert_sql
    assert insert_params is not None
    assert insert_params["position_id"] == "pos-001"
    assert insert_params["alert_type"] == "out_of_range"
    # Payload is JSON-serialised before binding so the same shape
    # works on JSONB (PG) and TEXT (SQLite).
    assert json.loads(insert_params["payload"]) == {
        "side": "upper",
        "ticks": 42,
    }


def test_get_open_alerts_filters_dismissed():
    """Insert 2 -> both open. Dismiss 1 -> only the other returned."""
    from src.storage.repositories.position_alert import (
        dismiss_alert,
        get_open_alerts,
        insert_alert,
    )

    session = _FakeSession()

    a1 = asyncio.run(
        insert_alert(
            session,
            position_id="pos-007",
            alert_type="out_of_range",
            payload={"k": 1},
        )
    )
    a2 = asyncio.run(
        insert_alert(
            session,
            position_id="pos-007",
            alert_type="fee_apr_drop",
            payload={"k": 2},
        )
    )
    assert (a1, a2) == (1, 2)

    open_before = asyncio.run(get_open_alerts(session, "pos-007"))
    assert len(open_before) == 2
    types_before = {a["alert_type"] for a in open_before}
    assert types_before == {"out_of_range", "fee_apr_drop"}

    # Round-trip the JSON payload too.
    payloads_before = sorted(a["payload"]["k"] for a in open_before)
    assert payloads_before == [1, 2]

    # Dismiss the first one and re-query.
    asyncio.run(dismiss_alert(session, a1))

    open_after = asyncio.run(get_open_alerts(session, "pos-007"))
    assert len(open_after) == 1
    assert open_after[0]["id"] == a2
    assert open_after[0]["alert_type"] == "fee_apr_drop"


def test_dismiss_alert_sets_dismissed_at():
    """dismiss_alert issues an UPDATE that flips dismissed_at non-null."""
    from src.storage.repositories.position_alert import (
        dismiss_alert,
        insert_alert,
    )

    session = _FakeSession()

    aid = asyncio.run(
        insert_alert(
            session,
            position_id="pos-042",
            alert_type="tvl_exodus",
            payload={"drop_pct": 31.2},
        )
    )
    # Pre-dismiss: the row's dismissed_at is NULL in the backing store.
    assert session._rows[0]["dismissed_at"] is None

    asyncio.run(dismiss_alert(session, aid))

    # Post-dismiss: the UPDATE landed and dismissed_at is now set.
    assert session._rows[0]["dismissed_at"] is not None
    # The SQL itself referenced the CURRENT_TIMESTAMP server-side so
    # the wall clock is the DB's, not the app server's.
    update_calls = [
        s for s in session.statements if "UPDATE position_alerts" in s[0]
    ]
    assert len(update_calls) == 1
    update_sql, update_params = update_calls[0]
    assert "dismissed_at = CURRENT_TIMESTAMP" in update_sql
    assert int(update_params["alert_id"]) == aid


def test_model_exposes_spec_attributes():
    """The PositionAlert ORM class exposes the spec-canonical
    attribute names (id, alert_type, payload, dismissed_at) even
    though the legacy PK column is still physically `alert_id`."""
    from src.storage.models.position_alert import PositionAlert

    assert PositionAlert.__tablename__ == "position_alerts"
    cols = {c.name for c in PositionAlert.__table__.columns}
    # Physical column name remains alert_id (we don't rename a PK in
    # an additive migration), but the spec cols are present.
    assert "alert_id" in cols
    assert "alert_type" in cols
    assert "payload" in cols
    assert "dismissed_at" in cols
    assert "fired_at" in cols
    assert "position_id" in cols

    # Spec attribute names land on the class.
    pa = PositionAlert()
    pa.position_id = "pos-X"
    pa.alert_type = "gas_favorable"
    pa.payload = {"gwei": 22}
    assert pa.position_id == "pos-X"
    assert pa.alert_type == "gas_favorable"
    assert pa.payload == {"gwei": 22}

    d = pa.to_dict()
    for k in ("id", "position_id", "alert_type", "fired_at", "payload", "dismissed_at"):
        assert k in d
