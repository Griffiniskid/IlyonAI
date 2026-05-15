"""LI.FI + Socket bridge clients conform to composed_plan.Bridge.

Tests use a stubbed httpx-shaped fake to avoid network I/O.
"""
from __future__ import annotations

import asyncio

import pytest

from src.routing.lifi_client import LifiBridge
from src.routing.socket_client import SocketBridge


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses: list[dict]):
        # Each get() consumes one response in order.
        self._responses = list(responses)

    async def get(self, url, params=None, headers=None):
        if not self._responses:
            raise RuntimeError("no more stubbed responses")
        return _FakeResponse(self._responses.pop(0))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def aclose(self):
        pass


# ── LI.FI ──

def test_lifi_quote_extracts_toAmount_and_slippage_band():
    fake = _FakeClient([
        {
            "id": "route-123",
            "tool": "across",
            "estimate": {
                "toAmount": "1000000",       # 1.0 USDC (6 dec) target
                "toAmountMin": "995000",     # 50 bps tolerance
                "executionDuration": 180,
            },
        }
    ])
    bridge = LifiBridge(http=fake)
    out = _run(bridge.quote(
        src_chain_id=1, dst_chain_id=137,
        token_in="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        token_out="0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
        amount=1_000_000, recipient="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ))
    assert out["expected_dst_amount"] == 1_000_000
    # 5_000 / 1_000_000 = 50 bps
    assert out["slippage_bps_band"]["max"] == 50
    assert out["quote_id"] == "route-123"
    assert out["ttl_s"] == 180
    assert out["via"] == "across"


def test_lifi_quote_handles_zero_toAmount_defensively():
    fake = _FakeClient([{"estimate": {}}])
    bridge = LifiBridge(http=fake)
    out = _run(bridge.quote(
        src_chain_id=1, dst_chain_id=42161,
        token_in="0x0", token_out="0x0", amount=1, recipient="0x0",
    ))
    assert out["expected_dst_amount"] == 0
    assert "slippage_bps_band" in out


def test_lifi_status_maps_DONE_to_filled():
    fake = _FakeClient([{
        "status": "DONE",
        "receiving": {"amount": "999000"},
    }])
    bridge = LifiBridge(http=fake)
    out = _run(bridge.status("0xtxhash"))
    assert out["state"] == "filled"
    assert out["actual_dst_amount"] == 999_000


def test_lifi_status_maps_FAILED_to_failed():
    fake = _FakeClient([{"status": "FAILED"}])
    bridge = LifiBridge(http=fake)
    out = _run(bridge.status("0xfailtx"))
    assert out["state"] == "failed"
    assert out["actual_dst_amount"] is None


def test_lifi_status_maps_PENDING_to_created():
    fake = _FakeClient([{"status": "PENDING"}])
    bridge = LifiBridge(http=fake)
    out = _run(bridge.status("0xpending"))
    assert out["state"] == "created"


def test_lifi_name_attribute():
    assert LifiBridge().name == "lifi"


# ── Socket ──

def test_socket_quote_extracts_routes_best_route():
    fake = _FakeClient([{
        "result": {
            "routes": [
                {
                    "toAmount": "997500",
                    "routeId": "route-abc",
                    "serviceTime": 300,
                    "usedBridgeNames": ["across-v2"],
                }
            ]
        }
    }])
    bridge = SocketBridge(api_key="test-key", http=fake)
    out = _run(bridge.quote(
        src_chain_id=1, dst_chain_id=8453,
        token_in="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        token_out="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        amount=1_000_000, recipient="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ))
    assert out["expected_dst_amount"] == 997_500
    assert out["quote_id"] == "route-abc"
    assert out["ttl_s"] == 300
    assert out["via"] == "across-v2"


def test_socket_quote_handles_no_routes():
    fake = _FakeClient([{"result": {"routes": []}}])
    bridge = SocketBridge(http=fake)
    out = _run(bridge.quote(
        src_chain_id=1, dst_chain_id=137, token_in="0x0",
        token_out="0x0", amount=1, recipient="0x0",
    ))
    assert out["expected_dst_amount"] == 0
    assert out["quote_id"] is None


def test_socket_status_maps_COMPLETED_to_filled():
    fake = _FakeClient([{
        "result": {
            "destinationTxStatus": "COMPLETED",
            "destinationTokenAmount": "997500",
        }
    }])
    bridge = SocketBridge(http=fake)
    out = _run(bridge.status("0xtxhash"))
    assert out["state"] == "filled"
    assert out["actual_dst_amount"] == 997_500


def test_socket_status_maps_FAILED_to_failed():
    fake = _FakeClient([{"result": {"destinationTxStatus": "FAILED"}}])
    bridge = SocketBridge(http=fake)
    out = _run(bridge.status("0xfailtx"))
    assert out["state"] == "failed"


def test_socket_name_attribute():
    assert SocketBridge().name == "socket"


def test_socket_includes_api_key_header_when_set():
    bridge = SocketBridge(api_key="my-secret-key")
    h = bridge._headers()
    assert h == {"API-KEY": "my-secret-key"}


def test_socket_omits_api_key_header_when_unset():
    bridge = SocketBridge(api_key="")
    assert bridge._headers() == {}


# ── Protocol conformance — duck-type ──

def test_lifi_conforms_to_bridge_protocol():
    """LifiBridge has .name, .quote, .status — duck-typed Bridge contract."""
    b = LifiBridge()
    assert isinstance(b.name, str)
    assert callable(b.quote) and asyncio.iscoroutinefunction(b.quote)
    assert callable(b.status) and asyncio.iscoroutinefunction(b.status)


def test_socket_conforms_to_bridge_protocol():
    b = SocketBridge()
    assert isinstance(b.name, str)
    assert callable(b.quote) and asyncio.iscoroutinefunction(b.quote)
    assert callable(b.status) and asyncio.iscoroutinefunction(b.status)
