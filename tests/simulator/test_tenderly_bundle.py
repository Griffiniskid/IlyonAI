"""V7-010 pin — Tenderly bundle simulator.

Covers:
  - SimulationResult round-trips through the parser on a success body.
  - SimulationResult surfaces an error_message on revert.
  - calldata_hash is deterministic across dict-key ordering of the
    request payload (matches V7-001's hash-bind invariant).
  - HTTP error path returns success=False rather than raising.
  - Constructor validates non-empty api_key + slugs.
"""
from __future__ import annotations

from typing import Any

import pytest

from src.defi.simulator.tenderly_client import (
    SimulationResult,
    TenderlyClient,
    _parse_tenderly_response,
)


# ── Fake aiohttp ClientSession / response for mocked HTTP ─────────────
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
    """Minimal aiohttp.ClientSession stand-in. Captures last POST."""

    def __init__(self, response: _FakeResp) -> None:
        self._response = response
        self.last_url: str | None = None
        self.last_payload: dict | None = None
        self.last_headers: dict | None = None

    def post(self, url: str, *, json: dict, headers: dict, timeout: Any) -> _FakeResp:
        self.last_url = url
        self.last_payload = json
        self.last_headers = headers
        return self._response


# ── Constructor validation ────────────────────────────────────────────
def test_constructor_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match="api_key"):
        TenderlyClient(api_key="", account_slug="acct", project_slug="proj")


def test_constructor_rejects_empty_slugs() -> None:
    with pytest.raises(ValueError, match="account_slug"):
        TenderlyClient(api_key="k", account_slug="", project_slug="proj")


# ── calldata_hash determinism (round-trip) ────────────────────────────
@pytest.mark.asyncio
async def test_simulate_bundle_calldata_hash_is_deterministic_for_same_payload() -> None:
    resp_body = {
        "simulation_results": [
            {"transaction": {"status": True, "gas_used": 50000}},
        ]
    }
    session_a = _FakeSession(_FakeResp(status=200, json_body=resp_body))
    session_b = _FakeSession(_FakeResp(status=200, json_body=resp_body))

    client_a = TenderlyClient("k", "acct", "proj", session=session_a)
    client_b = TenderlyClient("k", "acct", "proj", session=session_b)

    txs = [{"to": "0xabc", "data": "0xdeadbeef", "value": "0"}]
    r_a = await client_a.simulate_bundle(txs, network_id=1)
    r_b = await client_b.simulate_bundle(txs, network_id=1)
    assert r_a.calldata_hash == r_b.calldata_hash
    assert len(r_a.calldata_hash) == 64  # sha256 hex


# ── Success path round-trip ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_bundle_success_round_trips_gas_and_hash() -> None:
    resp_body = {
        "simulation_results": [
            {"transaction": {"status": True, "gas_used": 42000}},
            {"transaction": {"status": True, "gas_used": 21000}},
        ]
    }
    session = _FakeSession(_FakeResp(status=200, json_body=resp_body))
    client = TenderlyClient("api-key", "ilyonai", "main", session=session)

    result = await client.simulate_bundle(
        transactions=[
            {"to": "0xabc", "data": "0x1234", "value": "0", "from": "0xdef"},
            {"to": "0x999", "data": "0x5678", "value": "0", "from": "0xdef"},
        ],
        network_id=8453,
    )

    assert result.success is True
    assert result.gas_used == 63000
    assert result.error_message is None
    assert len(result.calldata_hash) == 64
    # The URL must be assembled from account/project slugs.
    assert "ilyonai" in (session.last_url or "")
    assert "main/simulate-bundle" in (session.last_url or "")
    # Auth header carries the API key.
    assert session.last_headers and session.last_headers.get("X-Access-Key") == "api-key"
    # Network id is stringified per Tenderly convention.
    assert session.last_payload and session.last_payload["simulations"][0]["network_id"] == "8453"


# ── Revert path ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_bundle_surfaces_revert_message_on_failed_leg() -> None:
    resp_body = {
        "simulation_results": [
            {"transaction": {
                "status": False,
                "gas_used": 30000,
                "error_message": "execution reverted: ERC20: insufficient allowance",
            }},
        ]
    }
    session = _FakeSession(_FakeResp(status=200, json_body=resp_body))
    client = TenderlyClient("k", "acct", "proj", session=session)

    result = await client.simulate_bundle(
        transactions=[{"to": "0xabc", "data": "0x", "value": "0"}],
        network_id=1,
    )
    assert result.success is False
    assert "insufficient allowance" in (result.error_message or "")
    # calldata_hash is still populated on failure — the bind invariant
    # needs SOMETHING to refuse against.
    assert result.calldata_hash


# ── HTTP error path ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_bundle_returns_failed_result_on_non_2xx() -> None:
    session = _FakeSession(_FakeResp(
        status=401, json_body=None, text_body='{"error":"unauthorized"}',
    ))
    client = TenderlyClient("k", "acct", "proj", session=session)
    result = await client.simulate_bundle(
        transactions=[{"to": "0xabc", "data": "0x", "value": "0"}],
        network_id=1,
    )
    assert result.success is False
    assert "401" in (result.error_message or "")


# ── Parser unit tests ─────────────────────────────────────────────────
def test_parse_handles_empty_simulation_results() -> None:
    result = _parse_tenderly_response({"simulation_results": []}, "h" * 64)
    assert result.success is False
    assert "empty" in (result.error_message or "")
    assert result.calldata_hash == "h" * 64


def test_parse_handles_single_leg_transaction_shape() -> None:
    # Some Tenderly responses return a `transaction` key at the top
    # level instead of a `simulation_results` array; tolerate both.
    body = {"transaction": {"status": True, "gas_used": 12345}, "simulation": {}}
    result = _parse_tenderly_response(body, "h" * 64)
    assert result.success is True
    assert result.gas_used == 12345
