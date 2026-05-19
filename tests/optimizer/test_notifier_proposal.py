"""Spec §9 notifier pin tests — `notify_proposal` writes a row + publishes.

Two complementary surfaces:

  - DB-less path: `db=None` → falls back to the in-memory pending list,
    returns a non-None row id, and pushes onto the in-process bus.
  - DB-backed path: real `Database` (SQLite) → row persisted into
    `position_alerts` with alert_type="proposal_pending", id returned,
    payload round-trips.
"""
from __future__ import annotations

import pytest

from src.optimizer.notifier import (
    get_pending_fallback,
    get_proposal_bus,
    notification_channel,
    notify_proposal,
    reset_pending_fallback,
    reset_proposal_bus,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_pending_fallback()
    reset_proposal_bus()
    yield
    reset_pending_fallback()
    reset_proposal_bus()


@pytest.mark.asyncio
async def test_notify_proposal_dbless_returns_id_and_falls_back():
    row_id = await notify_proposal(
        user_id=42,
        plan_id="plan-abc",
        title="Rebalance ETH/USDC 5bp",
        db=None,
        payload={"drift_bps": 78.4, "protocol": "uniswap_v3"},
    )
    assert row_id is not None
    assert row_id == 1  # first entry in the in-memory fallback

    pending = get_pending_fallback()
    assert len(pending) == 1
    entry = pending[0]
    assert entry["plan_id"] == "plan-abc"
    assert entry["user_id"] == 42
    assert entry["title"] == "Rebalance ETH/USDC 5bp"
    assert entry["drift_bps"] == pytest.approx(78.4)
    assert entry["protocol"] == "uniswap_v3"


@pytest.mark.asyncio
async def test_notify_proposal_publishes_to_bus_for_active_subscriber():
    bus = get_proposal_bus()
    q = bus.subscribe(user_id=42)

    row_id = await notify_proposal(
        user_id=42,
        plan_id="plan-xyz",
        title="Move to higher-APR pool",
        db=None,
    )
    assert row_id is not None

    # Subscriber should have received the payload.
    assert q.qsize() == 1
    payload = await q.get()
    assert payload["kind"] == "proposal_pending"
    assert payload["plan_id"] == "plan-xyz"
    assert payload["row_id"] == row_id
    assert payload["title"] == "Move to higher-APR pool"


@pytest.mark.asyncio
async def test_notify_proposal_does_not_leak_across_users():
    bus = get_proposal_bus()
    q_alice = bus.subscribe(user_id=1)
    q_bob = bus.subscribe(user_id=2)

    await notify_proposal(user_id=1, plan_id="p1", title="t1", db=None)

    assert q_alice.qsize() == 1
    assert q_bob.qsize() == 0


@pytest.mark.asyncio
async def test_notify_proposal_persists_to_database():
    """End-to-end DB write — uses an isolated in-memory SQLite engine
    so the test does not touch the dev/staging database.

    Table created via raw SQL so the PK column matches the V7-023
    physical schema (`alert_id INTEGER PRIMARY KEY AUTOINCREMENT` on
    SQLite). The notifier routes through the repo helper which probes
    the dialect and uses `last_insert_rowid()` for SQLite.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE position_alerts (
                    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id TEXT NOT NULL,
                    alert_type TEXT,
                    fired_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    payload TEXT,
                    dismissed_at TEXT
                )
                """
            )
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    class _FakeDB:
        _initialized = True
        async_session = session_factory

    fake_db = _FakeDB()

    row_id = await notify_proposal(
        user_id=99,
        plan_id="plan-db-1",
        title="Rebalance Raydium CLMM SOL/USDC",
        db=fake_db,
        payload={"chain_id": 101, "drift_bps": 120.0},
    )
    assert row_id is not None
    assert isinstance(row_id, int) and row_id > 0

    # Read back via the repo helper so we exercise the same dialect
    # path that the notifier used to write.
    from src.storage.repositories.position_alert import get_open_alerts

    async with session_factory() as session:
        rows = await get_open_alerts(session, position_id="plan-db-1")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == row_id
    assert row["alert_type"] == "proposal_pending"
    assert row["position_id"] == "plan-db-1"
    payload = row["payload"]
    assert payload["plan_id"] == "plan-db-1"
    assert payload["user_id"] == 99
    assert payload["title"] == "Rebalance Raydium CLMM SOL/USDC"
    assert payload["chain_id"] == 101
    assert payload["drift_bps"] == 120.0


def test_notification_channel_picks_sse_when_session_active():
    assert notification_channel(has_active_session=True) == "sse"
    assert notification_channel(has_active_session=False) == "email"
