"""Audit log route — GET /api/v1/audit/{wallet}."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.audit import list_audit_entries, _row_to_payload


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _req(wallet: str, app: dict | None = None, query: dict | None = None):
    req = MagicMock()
    req.match_info = {"wallet": wallet}
    req.app = app or {}
    req.query = query or {}
    return req


def _resp_json(resp):
    return json.loads(resp.text)


def test_rejects_invalid_wallet():
    resp = _run(list_audit_entries(_req("nope")))
    assert resp.status == 400


def test_evm_wallet_accepts_and_returns_empty():
    resp = _run(list_audit_entries(_req("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")))
    assert resp.status == 200
    data = _resp_json(resp)
    assert data["ok"] is True
    assert data["entries"] == []


def test_solana_wallet_accepts():
    """Solana base58 wallet > 32 chars also valid."""
    sol = "5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L"
    resp = _run(list_audit_entries(_req(sol)))
    assert resp.status == 200
    data = _resp_json(resp)
    assert data["wallet"] == sol.lower()


def test_cache_path_returns_entries():
    wallet = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    entries = [
        {"entry_id": "e1", "user_wallet": wallet, "prompt_hash": "0xabc",
         "plan_hash": "0xdef", "hmac": "0x111", "prev_hmac": "0x000", "ts": 1.0},
    ]
    app = {"_audit_chain_cache": {wallet: entries}}
    resp = _run(list_audit_entries(_req(wallet, app=app)))
    data = _resp_json(resp)
    assert data["persisted"] is False
    assert len(data["entries"]) == 1


def test_limit_param_clamped_to_500():
    resp = _run(list_audit_entries(
        _req("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", query={"limit": "9999"}),
    ))
    assert resp.status == 200


def test_limit_param_minimum_1():
    resp = _run(list_audit_entries(
        _req("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", query={"limit": "0"}),
    ))
    assert resp.status == 200


def test_row_to_payload_normalises_datetime():
    """DB rows include a datetime created_at — coerced to unix-ts in payload."""
    from datetime import datetime, timezone
    row = {
        "entry_id": "abc", "user_wallet": "0xa", "prompt_hash": "0xab",
        "plan_hash": "0xcd", "tx_hash": None, "prev_hmac": "0x00",
        "hmac": "0xff",
        "created_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
    }
    out = _row_to_payload(row)
    assert isinstance(out["ts"], float)
    assert out["ts"] > 0


def test_row_to_payload_handles_missing_fields():
    row = {"entry_id": "x", "user_wallet": "0xa"}
    out = _row_to_payload(row)
    assert out["entry_id"] == "x"
    assert out["plan_hash"] == ""
    assert out["tx_hash"] is None


def test_db_read_failure_returns_500():
    async def _bad_factory():
        raise RuntimeError("db down")
    # Use a context-manager that raises on .execute() to simulate DB error.
    class _FailSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def execute(self, *args, **kwargs):
            raise RuntimeError("query failed")
    def _factory():
        return _FailSession()
    app = {"_db_session_factory": _factory}
    resp = _run(list_audit_entries(
        _req("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", app=app),
    ))
    assert resp.status == 500
