"""V7-075 — Pin test for the unified intent_state store + agent_013 migration.

Verifies:
  1. Migration module loads cleanly (alembic.op stub pattern from
     V7-004 / V7-023) and declares agent_013 -> agent_012.
  2. `upsert_intent_state` binds the canonical params and JSON-encodes
     the payload before binding.
  3. `get_intent_state` round-trips the same intent_id → returns the
     persisted dict with payload re-parsed back to a native dict.
  4. A second `upsert_intent_state` on the same intent_id mutates
     status + current_step + payload (the UPSERT path, not a duplicate
     INSERT).
  5. `get_intent_state` returns None on miss.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any


class _Result:
    """Mimics SQLAlchemy `Result` for the surface state_store uses."""

    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict]:
        return list(self._rows)

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """In-memory async session double — records statements + backs an
    intent_state dict so upsert -> get -> upsert -> get round trips."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict | None]] = []
        self._rows: dict[str, dict] = {}
        self.bind = type(
            "B",
            (),
            {"dialect": type("D", (), {"name": "sqlite"})()},
        )()

    async def execute(self, statement, params=None, *a, **kw) -> _Result:
        sql = str(statement)
        self.statements.append((sql, params))
        sql_upper = sql.upper()

        if "INSERT INTO INTENT_STATE" in sql_upper:
            assert params is not None
            iid = params["intent_id"]
            # Upsert: overwrite on conflict.
            self._rows[iid] = {
                "intent_id": iid,
                "status": params["status"],
                "current_step": params["current_step"],
                "payload": params["payload"],  # already JSON-encoded string
                "updated_at": "2026-05-18T00:00:00Z",
            }
            return _Result([])

        if "SELECT" in sql_upper and "INTENT_STATE" in sql_upper:
            assert params is not None
            iid = params["intent_id"]
            row = self._rows.get(iid)
            return _Result([row]) if row is not None else _Result([])

        return _Result([])


# ─── Migration import test ────────────────────────────────────────────────


def test_migration_module_imports_cleanly():
    """agent_013 parses, declares agent_013 -> agent_012 chain, and
    upgrade()/downgrade() smoke-call against a stubbed alembic.op.

    Mirrors the V7-004 / V7-023 loader so the test runs without alembic.
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
        / "20260518_agent_013_intent_state.py"
    )
    assert mig_path.exists(), f"migration file missing: {mig_path}"

    if "alembic" not in sys.modules:
        alembic_stub = types.ModuleType("alembic")
        op_stub = types.SimpleNamespace(
            add_column=lambda *a, **kw: None,
            drop_column=lambda *a, **kw: None,
            create_index=lambda *a, **kw: None,
            drop_index=lambda *a, **kw: None,
            create_table=lambda *a, **kw: None,
            drop_table=lambda *a, **kw: None,
            get_bind=lambda: None,
        )
        alembic_stub.op = op_stub
        sys.modules["alembic"] = alembic_stub
    else:
        op = sys.modules["alembic"].op
        for name in (
            "add_column",
            "drop_column",
            "create_index",
            "drop_index",
            "create_table",
            "drop_table",
        ):
            if not hasattr(op, name):
                setattr(op, name, lambda *a, **kw: None)
        if not hasattr(op, "get_bind"):
            op.get_bind = lambda: None  # type: ignore[attr-defined]

    spec = importlib.util.spec_from_file_location(
        "agent_013_intent_state", str(mig_path)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "agent_013"
    assert mod.down_revision == "agent_012"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    mod.upgrade()
    mod.downgrade()


# ─── Repo round-trip tests ────────────────────────────────────────────────


def test_upsert_binds_canonical_params_and_json_encodes_payload():
    """upsert_intent_state binds intent_id/status/current_step/payload
    and the payload is JSON-encoded before the bind."""
    from src.storage.state_store import upsert_intent_state

    session = _FakeSession()
    asyncio.run(
        upsert_intent_state(
            session,
            intent_id="intent-001",
            status="READY_TO_SIGN",
            current_step=0,
            payload={"plan_id": "plan_abc", "chain": "base"},
        )
    )

    assert len(session.statements) == 1
    sql, params = session.statements[0]
    assert "INSERT INTO intent_state" in sql
    assert params is not None
    assert params["intent_id"] == "intent-001"
    assert params["status"] == "READY_TO_SIGN"
    assert params["current_step"] == 0
    # Payload is JSON-encoded before binding so the wire shape is
    # identical between JSONB (PG) and JSON-text (SQLite).
    assert json.loads(params["payload"]) == {"plan_id": "plan_abc", "chain": "base"}


def test_upsert_then_get_round_trips():
    """upsert -> get returns the canonical dict with payload re-parsed."""
    from src.storage.state_store import get_intent_state, upsert_intent_state

    session = _FakeSession()
    asyncio.run(
        upsert_intent_state(
            session,
            intent_id="intent-rt",
            status="DRAFTING",
            current_step=2,
            payload={"step": "approve", "spender": "0xabc"},
        )
    )

    out = asyncio.run(get_intent_state(session, "intent-rt"))
    assert out is not None
    assert out["intent_id"] == "intent-rt"
    assert out["status"] == "DRAFTING"
    assert out["current_step"] == 2
    # Payload is back to a native dict (re-parsed from the JSON string).
    assert out["payload"] == {"step": "approve", "spender": "0xabc"}


def test_second_upsert_updates_status_and_payload():
    """The UPSERT path overwrites status / current_step / payload on
    re-entry rather than producing a duplicate row."""
    from src.storage.state_store import get_intent_state, upsert_intent_state

    session = _FakeSession()
    iid = "intent-mut"

    asyncio.run(
        upsert_intent_state(
            session,
            intent_id=iid,
            status="DRAFTING",
            current_step=0,
            payload={"k": "v0"},
        )
    )
    asyncio.run(
        upsert_intent_state(
            session,
            intent_id=iid,
            status="READY_TO_SIGN",
            current_step=1,
            payload={"k": "v1", "extra": True},
        )
    )

    out = asyncio.run(get_intent_state(session, iid))
    assert out is not None
    assert out["status"] == "READY_TO_SIGN"
    assert out["current_step"] == 1
    assert out["payload"] == {"k": "v1", "extra": True}


def test_get_returns_none_on_miss():
    """No row for the intent_id → get returns None (not a raise)."""
    from src.storage.state_store import get_intent_state

    session = _FakeSession()
    out = asyncio.run(get_intent_state(session, "never-seen"))
    assert out is None


def test_upsert_rejects_empty_intent_id():
    """Defensive: empty intent_id is a ValueError, never silently
    persists into a row at PK=''."""
    import pytest

    from src.storage.state_store import upsert_intent_state

    with pytest.raises(ValueError):
        asyncio.run(
            upsert_intent_state(
                _FakeSession(),
                intent_id="",
                status="DRAFTING",
                current_step=0,
                payload={},
            )
        )
