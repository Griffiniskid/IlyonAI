"""Tests for src/defi/audit_persistence.py."""
from __future__ import annotations

import asyncio
import json

from src.defi.audit_persistence import (
    _entry_to_row,
    persist_entry,
    persist_chain,
    read_chain_for_user,
)
from src.defi.audit_trail import sign_audit_entry


class _FakeSession:
    def __init__(self):
        self.statements: list[tuple[str, dict | None]] = []

    async def execute(self, statement, params=None, *a, **kw):
        self.statements.append((str(statement), params))

        class _R:
            def mappings(self):
                return self
            def all(self):
                return []
        return _R()


def _make_entry():
    return sign_audit_entry(
        key=b"k" * 32,
        prompt="user prompt",
        plan_dict={"steps": []},
        tx_hash="0xtx",
    )


def test_entry_to_row_carries_context():
    e = _make_entry()
    row = _entry_to_row(e, policy_id="pol-1", user_wallet="0xAAA", action="supply",
                       payload={"x": 1})
    assert row["policy_id"] == "pol-1"
    assert row["user_wallet"] == "0xaaa"
    assert row["action"] == "supply"
    assert row["entry_hmac"] == e.entry_hmac
    assert row["timestamp"] == e.timestamp
    assert json.loads(row["payload_json"]) == {"x": 1}


def test_persist_entry_emits_insert():
    e = _make_entry()
    session = _FakeSession()
    asyncio.run(persist_entry(session, e, policy_id="pol-1", user_wallet="0xa", action="supply"))
    sql, params = session.statements[0]
    assert "INSERT INTO session_key_audit_log" in sql
    assert params["entry_hmac"] == e.entry_hmac


def test_persist_chain_iterates():
    e1 = _make_entry()
    e2 = _make_entry()
    session = _FakeSession()
    n = asyncio.run(persist_chain(session, [e1, e2], policy_id="p", user_wallet="0xa"))
    assert n == 2
    assert len(session.statements) == 2


def test_read_chain_for_user_filters_by_wallet():
    session = _FakeSession()
    asyncio.run(read_chain_for_user(session, user_wallet="0xABCD"))
    sql, params = session.statements[0]
    assert "WHERE user_wallet = :w" in sql
    assert params["w"] == "0xabcd"


def test_payload_json_none_when_empty():
    e = _make_entry()
    row = _entry_to_row(e, policy_id="p", user_wallet="0xa", action="x", payload=None)
    assert row["payload_json"] is None
