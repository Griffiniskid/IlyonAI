"""EIP-7702 auth route handlers — unit-tested without an HTTP server."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from src.api.routes.eip7702_auth import (
    authorize,
    list_authorizations,
    prepare_authorization,
    setup_eip7702_routes,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mock_request(body: dict, match: dict | None = None) -> MagicMock:
    """Build a request that hands `body` back via .json()."""
    req = MagicMock()
    req.json = AsyncMock(return_value=body)
    req.match_info = match or {}
    req.app = {"_eip7702_auths": {}}
    return req


def _resp_json(resp: web.Response) -> dict:
    return json.loads(resp.text)


def test_prepare_returns_digest_for_nexus():
    r = _mock_request({
        "wallet": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "chain_id": 1, "nonce": 0, "impl": "nexus",
    })
    resp = _run(prepare_authorization(r))
    assert resp.status == 200
    data = _resp_json(resp)
    assert data["ok"] is True
    assert data["impl"] == "0x000000aC74357BFEa72BBD0781833631F732cf19"
    assert data["impl_kind"] == "nexus"
    assert data["digest"].startswith("0x")


def test_prepare_returns_digest_for_kernel():
    r = _mock_request({
        "wallet": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "chain_id": 1, "nonce": 0, "impl": "kernel",
    })
    resp = _run(prepare_authorization(r))
    data = _resp_json(resp)
    assert data["impl"] == "0xd6CEDDe84be40893d153Be9d467CD6aD37875b28"
    assert data["impl_kind"] == "kernel"


def test_prepare_defaults_to_nexus():
    r = _mock_request({
        "wallet": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "chain_id": 1, "nonce": 0,
    })
    data = _resp_json(_run(prepare_authorization(r)))
    assert data["impl_kind"] == "nexus"


def test_prepare_rejects_invalid_wallet():
    r = _mock_request({"wallet": "not-an-address", "chain_id": 1, "nonce": 0})
    resp = _run(prepare_authorization(r))
    assert resp.status == 400


def test_prepare_rejects_unsupported_chain():
    r = _mock_request({
        "wallet": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "chain_id": 999_999, "nonce": 0,
    })
    resp = _run(prepare_authorization(r))
    assert resp.status == 400


def test_prepare_rejects_unknown_impl():
    r = _mock_request({
        "wallet": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "chain_id": 1, "nonce": 0, "impl": "imaginary-impl",
    })
    resp = _run(prepare_authorization(r))
    assert resp.status == 400


def test_authorize_rejects_invalid_signature():
    r = _mock_request({
        "wallet": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "chain_id": 1, "nonce": 0, "impl": "nexus",
        "signature_hex": "0xshort",
    })
    resp = _run(authorize(r))
    assert resp.status == 400


def test_authorize_dev_mode_caches_inapp():
    fake_sig = "0x" + ("ab" * 32) + ("cd" * 32) + "1c"
    r = _mock_request({
        "wallet": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "chain_id": 1, "nonce": 0, "impl": "nexus",
        "signature_hex": fake_sig,
    })
    resp = _run(authorize(r))
    assert resp.status == 200
    data = _resp_json(resp)
    assert data["ok"] is True
    assert data["persisted"] is False
    assert data["impl_addr"].lower() == "0x000000ac74357bfea72bbd0781833631f732cf19"


def test_list_rejects_invalid_wallet():
    r = _mock_request({}, match={"wallet": "not-a-wallet"})
    resp = _run(list_authorizations(r))
    assert resp.status == 400


def test_list_returns_empty_when_no_cache():
    r = _mock_request({}, match={"wallet": "0xcccccccccccccccccccccccccccccccccccccccc"})
    resp = _run(list_authorizations(r))
    data = _resp_json(resp)
    assert data["authorizations"] == []


def test_authorize_then_list_roundtrip():
    """Cache roundtrip — authorize → list returns the cached row."""
    fake_sig = "0x" + ("ab" * 32) + ("cd" * 32) + "1c"
    wallet = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    shared_app: dict = {"_eip7702_auths": {}}
    auth_req = MagicMock()
    auth_req.json = AsyncMock(return_value={
        "wallet": wallet, "chain_id": 1, "nonce": 7, "impl": "nexus",
        "signature_hex": fake_sig,
    })
    auth_req.app = shared_app
    auth_req.match_info = {}
    list_req = MagicMock()
    list_req.app = shared_app
    list_req.match_info = {"wallet": wallet}
    _run(authorize(auth_req))
    data = _resp_json(_run(list_authorizations(list_req)))
    assert len(data["authorizations"]) == 1
    assert data["authorizations"][0]["nonce"] == 7


def test_routes_register_under_eip7702_prefix():
    """Routes mount at /api/v1/eip7702/* (NOT /api/v1/auth/*) so Caddy
    falls through to the aiohttp app instead of hitting the uvicorn
    auth front. Regression pin for the 404 caught on staging."""
    from aiohttp import web
    app = web.Application()
    setup_eip7702_routes(app)
    paths = {r.resource.canonical for r in app.router.routes()}
    assert "/api/v1/eip7702/prepare" in paths
    assert "/api/v1/eip7702/authorize" in paths
    # auth-prefixed paths must NOT be registered.
    assert "/api/v1/auth/eip7702/prepare" not in paths


def test_prepare_handles_bad_json():
    req = MagicMock()
    req.json = AsyncMock(side_effect=RuntimeError("bad json"))
    req.app = {}
    req.match_info = {}
    resp = _run(prepare_authorization(req))
    assert resp.status == 400
    data = _resp_json(resp)
    assert data["error"] == "bad_json"
