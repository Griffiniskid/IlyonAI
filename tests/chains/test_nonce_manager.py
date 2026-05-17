"""V7-039 pin tests — pending-nonce management.

Covers:
- Hex string ``"0x5"`` → 5
- Raw int ``5`` → 5
- Hex string ``"0x10"`` → 16
- :py:meth:`EVMChainClient.next_nonce` delegates to
  :func:`get_next_nonce` and passes the ``pending`` block tag.
"""
from __future__ import annotations

from typing import Any, List
from unittest.mock import AsyncMock

import pytest

from src.chains.evm.nonce_manager import get_next_nonce


ADDR = "0x1234567890AbcdEF1234567890aBcdef12345678"


class _FakeClient:
    """Minimal stand-in exposing ``call_rpc`` like the spec describes."""

    def __init__(self, result: Any):
        self._result = result
        self.calls: List[tuple] = []

    async def call_rpc(self, method: str, params: list) -> Any:
        self.calls.append((method, tuple(params)))
        return self._result


@pytest.mark.asyncio
async def test_get_next_nonce_hex_small() -> None:
    client = _FakeClient("0x5")
    nonce = await get_next_nonce(client, ADDR)
    assert nonce == 5
    # Verify we asked for pending, not latest.
    assert client.calls == [("eth_getTransactionCount", (ADDR, "pending"))]


@pytest.mark.asyncio
async def test_get_next_nonce_raw_int() -> None:
    client = _FakeClient(5)
    nonce = await get_next_nonce(client, ADDR)
    assert nonce == 5


@pytest.mark.asyncio
async def test_get_next_nonce_hex_larger() -> None:
    client = _FakeClient("0x10")
    nonce = await get_next_nonce(client, ADDR)
    assert nonce == 16


@pytest.mark.asyncio
async def test_get_next_nonce_decimal_string() -> None:
    # Some non-standard providers return decimal strings; we accept them.
    client = _FakeClient("42")
    nonce = await get_next_nonce(client, ADDR)
    assert nonce == 42


@pytest.mark.asyncio
async def test_evm_client_next_nonce_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``EVMChainClient.next_nonce`` should call ``get_next_nonce`` and
    pass the wallet address straight through, using ``pending`` tag."""
    from src.chains.base import ChainConfig, ChainType
    from src.chains.evm.client import EVMChainClient

    config = ChainConfig(
        chain_type=ChainType.ETHEREUM,
        rpc_url="http://localhost:8545",
    )
    client = EVMChainClient(config)

    # Stub the underlying ``_rpc_call`` so we never touch the network.
    rpc_mock = AsyncMock(return_value="0x2a")
    client._rpc_call = rpc_mock  # type: ignore[assignment]

    nonce = await client.next_nonce(ADDR)

    assert nonce == 42
    rpc_mock.assert_awaited_once_with("eth_getTransactionCount", [ADDR, "pending"])
