"""V7-022 pin tests for `position_snapshots` repo + migration.

Mirrors the V7-004 pattern: FakeSession that records SQL + params,
alembic.op stub so the migration module can be imported and its
upgrade()/downgrade() smoke-called without a live alembic context.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations"
    / "versions"
    / "20260517_agent_011_position_snapshots.py"
)


# ──────────────────────────────────────────────────────────────────────
# Fakes
# ──────────────────────────────────────────────────────────────────────


class _MappingsResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict]:
        return list(self._rows)


class _Result:
    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []

    def mappings(self) -> _MappingsResult:
        return _MappingsResult(self._rows)


class _FakeSession:
    """Records every SQL text + params dict for assertion in tests.

    Simulates SQLite-style autoincrement: each INSERT bumps an internal
    counter, returned by the follow-up `SELECT last_insert_rowid()`.
    """

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict]] = []
        self._rows: list[dict] = []
        self._next_id: int = 1
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    async def execute(self, statement: Any, params: dict | None = None) -> _Result:
        sql_text = str(statement)
        self.statements.append((sql_text, dict(params or {})))

        if "INSERT INTO position_snapshots" in sql_text:
            row = {
                "id": self._next_id,
                "position_id": (params or {}).get("position_id"),
                "snapshot_at": f"2026-05-17T00:00:0{self._next_id % 10}Z",
                "payload": (params or {}).get("payload"),
            }
            self._rows.append(row)
            self._next_id += 1
            return _Result([])

        if "last_insert_rowid" in sql_text:
            return _Result([{"id": self._next_id - 1}])

        if "SELECT" in sql_text and "FROM position_snapshots" in sql_text:
            pid = (params or {}).get("position_id")
            limit = int((params or {}).get("limit", 1))
            matching = [r for r in self._rows if r["position_id"] == pid]
            matching.sort(key=lambda r: r["id"], reverse=True)
            return _Result(matching[:limit])

        return _Result([])


# ──────────────────────────────────────────────────────────────────────
# Migration smoke
# ──────────────────────────────────────────────────────────────────────


def _load_migration() -> ModuleType:
    """Load the agent_011 migration module with a stubbed `alembic.op`.

    alembic is not installed in the unit-test env, so we inject a
    minimal stub before importing the module. Only the surface used
    by upgrade()/downgrade() is stubbed (add_column / create_index /
    drop_column / drop_index).
    """
    calls: list[tuple[str, tuple, dict]] = []

    def _record(name: str):
        def _impl(*args, **kwargs):
            calls.append((name, args, kwargs))

        return _impl

    op_stub = ModuleType("alembic.op")
    op_stub.add_column = _record("add_column")  # type: ignore[attr-defined]
    op_stub.drop_column = _record("drop_column")  # type: ignore[attr-defined]
    op_stub.create_index = _record("create_index")  # type: ignore[attr-defined]
    op_stub.drop_index = _record("drop_index")  # type: ignore[attr-defined]

    alembic_stub = ModuleType("alembic")
    alembic_stub.op = op_stub  # type: ignore[attr-defined]

    sys.modules.setdefault("alembic", alembic_stub)
    sys.modules["alembic.op"] = op_stub

    spec = importlib.util.spec_from_file_location(
        "v7_022_position_snapshots_migration", str(MIGRATION_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module._captured_calls = calls  # type: ignore[attr-defined]
    spec.loader.exec_module(module)
    return module


def test_migration_module_imports_cleanly() -> None:
    module = _load_migration()
    assert module.revision == "agent_011"
    assert module.down_revision == "agent_010"
    module.upgrade()
    module.downgrade()
    names = [c[0] for c in module._captured_calls]  # type: ignore[attr-defined]
    assert "add_column" in names
    assert "drop_column" in names


# ──────────────────────────────────────────────────────────────────────
# Repo round-trip
# ──────────────────────────────────────────────────────────────────────


def test_insert_snapshot_round_trips_payload() -> None:
    from src.storage.repositories.position_snapshot import insert_snapshot

    session = _FakeSession()
    rowid = asyncio.run(
        insert_snapshot(session, "pos-001", {"il_pct": -1.2, "in_range": True})
    )
    assert rowid == 1

    sql, params = session.statements[0]
    assert "INSERT INTO position_snapshots" in sql
    assert params["position_id"] == "pos-001"
    assert params["payload"] is not None
    assert "il_pct" in params["payload"]


def test_get_latest_snapshots_returns_newest_first() -> None:
    from src.storage.repositories.position_snapshot import (
        get_latest_snapshots,
        insert_snapshot,
    )

    session = _FakeSession()
    asyncio.run(insert_snapshot(session, "pos-002", {"n": 1}))
    asyncio.run(insert_snapshot(session, "pos-002", {"n": 2}))
    asyncio.run(insert_snapshot(session, "pos-002", {"n": 3}))

    latest_one = asyncio.run(get_latest_snapshots(session, "pos-002", limit=1))
    assert len(latest_one) == 1
    assert latest_one[0]["payload"] == {"n": 3}


def test_get_latest_snapshots_respects_limit() -> None:
    from src.storage.repositories.position_snapshot import (
        get_latest_snapshots,
        insert_snapshot,
    )

    session = _FakeSession()
    for i in range(5):
        asyncio.run(insert_snapshot(session, "pos-003", {"n": i}))

    latest = asyncio.run(get_latest_snapshots(session, "pos-003", limit=2))
    assert len(latest) == 2
    assert [row["payload"]["n"] for row in latest] == [4, 3]


def test_model_exposes_spec_contract_attrs() -> None:
    from src.storage.models.position_snapshot import PositionSnapshot

    for attr in ("id", "position_id", "snapshot_at", "payload"):
        assert hasattr(PositionSnapshot, attr), f"missing attr {attr!r}"
    assert PositionSnapshot.__tablename__ == "position_snapshots"
