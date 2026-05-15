"""Permit2 signature handoff — attach + read."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.plan_permit2 import (
    attach_permit2_signature,
    read_permit2_signature,
    setup_plan_permit2_routes,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _req(body: dict | None, match: dict, app: dict | None = None):
    req = MagicMock()
    req.json = AsyncMock(return_value=body or {})
    req.match_info = match
    # Don't use `or` — caller may pass an empty dict they want preserved.
    req.app = app if app is not None else {}
    return req


def _resp_json(resp):
    return json.loads(resp.text)


def test_attach_caches_signature():
    app: dict = {}
    body = {
        "signature": "0x" + "ab" * 65,
        "permit": {
            "details": {"token": "0xa", "amount": "100", "expiration": 1234, "nonce": 0},
            "spender": "0xb",
            "sigDeadline": "9999",
        },
    }
    req = _req(body, match={"plan_id": "p1", "step_id": "s1"}, app=app)
    resp = _run(attach_permit2_signature(req))
    assert resp.status == 200
    data = _resp_json(resp)
    assert data["ok"] is True
    assert data["cached"] is True
    assert "_permit2_signatures" in app
    assert "p1:s1" in app["_permit2_signatures"]


def test_attach_rejects_invalid_signature():
    req = _req(
        {"signature": "not-a-sig", "permit": {}},
        match={"plan_id": "p1", "step_id": "s1"},
    )
    resp = _run(attach_permit2_signature(req))
    assert resp.status == 400


def test_attach_rejects_non_dict_permit():
    req = _req(
        {"signature": "0xab", "permit": "not-a-dict"},
        match={"plan_id": "p1", "step_id": "s1"},
    )
    resp = _run(attach_permit2_signature(req))
    assert resp.status == 400


def test_attach_handles_bad_json():
    req = MagicMock()
    req.json = AsyncMock(side_effect=RuntimeError("bad"))
    req.match_info = {"plan_id": "p", "step_id": "s"}
    req.app = {}
    resp = _run(attach_permit2_signature(req))
    assert resp.status == 400


def test_read_returns_cached_signature():
    app = {"_permit2_signatures": {"p1:s1": {"signature": "0xab", "permit": {}}}}
    req = _req(None, match={"plan_id": "p1", "step_id": "s1"}, app=app)
    resp = _run(read_permit2_signature(req))
    data = _resp_json(resp)
    assert data["ok"] is True
    assert data["signature"] == "0xab"


def test_read_unknown_returns_404():
    req = _req(None, match={"plan_id": "p1", "step_id": "s1"})
    resp = _run(read_permit2_signature(req))
    assert resp.status == 404


def test_attach_then_read_roundtrip():
    app: dict = {}
    body = {
        "signature": "0x" + "cd" * 65,
        "permit": {"details": {"token": "0xa"}, "spender": "0xb"},
    }
    _run(attach_permit2_signature(
        _req(body, match={"plan_id": "p2", "step_id": "s2"}, app=app),
    ))
    resp = _run(read_permit2_signature(
        _req(None, match={"plan_id": "p2", "step_id": "s2"}, app=app),
    ))
    data = _resp_json(resp)
    assert data["signature"] == body["signature"]


def test_routes_register_under_expected_paths():
    from aiohttp import web
    app = web.Application()
    setup_plan_permit2_routes(app)
    paths = {r.resource.canonical for r in app.router.routes()}
    assert "/api/v1/plans/{plan_id}/steps/{step_id}/permit2" in paths
