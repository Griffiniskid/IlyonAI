"""V7-010 pin — Solana simulateTransaction with replaceRecentBlockhash.

Covers:
  - success path: err=None + unitsConsumed populated → success=True
  - program error path: InstructionError → success=False + msg
  - RPC-level error path: top-level "error" → success=False
  - calldata_hash is deterministic across calls with the same serialized tx
  - request body carries replaceRecentBlockhash=True + sigVerify=False
"""
from __future__ import annotations

from typing import Any

import pytest

from src.defi.simulator.solana_simulator import (
    _parse_solana_response,
    simulate_transaction,
)


# ── Fake aiohttp session ──────────────────────────────────────────────
class _FakeResp:
    def __init__(self, *, status: int = 200, json_body: dict | None = None,
                 text_body: str = "") -> None:
        self.status = status
        self._json = json_body
        self._text = text_body or (str(json_body) if json_body else "")

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def text(self) -> str:
        return self._text

    async def json(self, content_type: str | None = None) -> dict:
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class _FakeSession:
    def __init__(self, response: _FakeResp) -> None:
        self._response = response
        self.last_url: str | None = None
        self.last_body: dict | None = None

    def post(self, url: str, *, json: dict, timeout: Any) -> _FakeResp:
        self.last_url = url
        self.last_body = json
        return self._response


# ── Success path ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_transaction_success_round_trips_compute_units() -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"value": {"err": None, "unitsConsumed": 18234, "logs": []}},
    }
    session = _FakeSession(_FakeResp(status=200, json_body=body))
    result = await simulate_transaction(
        "https://api.mainnet-beta.solana.com",
        "AbCdEf123==",  # placeholder base64 wire tx
        session=session,
    )
    assert result.success is True
    assert result.compute_units == 18234
    assert result.error_message is None
    assert len(result.calldata_hash) == 64

    # Request body must carry the V7-010-required sim flags.
    assert session.last_body is not None
    params = session.last_body["params"]
    assert params[0] == "AbCdEf123=="
    assert params[1]["replaceRecentBlockhash"] is True
    assert params[1]["sigVerify"] is False
    assert params[1]["encoding"] == "base64"


# ── Program error path ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_transaction_program_error_surfaces_err_message() -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"value": {
            "err": {"InstructionError": [0, {"Custom": 6000}]},
            "unitsConsumed": 4321,
            "logs": ["Program log: insufficient funds"],
        }},
    }
    session = _FakeSession(_FakeResp(status=200, json_body=body))
    result = await simulate_transaction(
        "https://api.mainnet-beta.solana.com",
        "AbCdEf==",
        session=session,
    )
    assert result.success is False
    assert "InstructionError" in (result.error_message or "")
    assert "Custom" in (result.error_message or "")
    assert result.compute_units == 4321
    # calldata_hash still populated on failure — needed for hash-bind logging.
    assert result.calldata_hash


# ── RPC-level error path ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_transaction_rpc_error_returns_failed_result() -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32602, "message": "invalid base64 encoding"},
    }
    session = _FakeSession(_FakeResp(status=200, json_body=body))
    result = await simulate_transaction(
        "https://api.mainnet-beta.solana.com",
        "not-actually-b64",
        session=session,
    )
    assert result.success is False
    assert "-32602" in (result.error_message or "")
    assert "invalid base64" in (result.error_message or "")


# ── HTTP error path ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_transaction_returns_failed_on_non_2xx() -> None:
    session = _FakeSession(_FakeResp(status=502, json_body=None, text_body="bad gateway"))
    result = await simulate_transaction(
        "https://api.mainnet-beta.solana.com", "AAA=", session=session,
    )
    assert result.success is False
    assert "502" in (result.error_message or "")


# ── Determinism (round-trip) ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_transaction_calldata_hash_is_deterministic() -> None:
    body = {"jsonrpc": "2.0", "id": 1, "result": {"value": {"err": None, "unitsConsumed": 1}}}
    s1 = _FakeSession(_FakeResp(status=200, json_body=body))
    s2 = _FakeSession(_FakeResp(status=200, json_body=body))
    r1 = await simulate_transaction("https://rpc", "TX-PAYLOAD-B64==", session=s1)
    r2 = await simulate_transaction("https://rpc", "TX-PAYLOAD-B64==", session=s2)
    assert r1.calldata_hash == r2.calldata_hash


# ── Parser unit tests ─────────────────────────────────────────────────
def test_parse_solana_response_with_err_none_is_success() -> None:
    result = _parse_solana_response(
        {"result": {"value": {"err": None, "unitsConsumed": 100}}},
        "h" * 64,
    )
    assert result.success is True
    assert result.compute_units == 100


def test_parse_solana_response_with_rpc_error_dict() -> None:
    result = _parse_solana_response(
        {"error": {"code": -32000, "message": "boom"}},
        "h" * 64,
    )
    assert result.success is False
    assert "-32000" in (result.error_message or "")
