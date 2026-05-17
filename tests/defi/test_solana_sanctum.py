"""Pin test — Sanctum S-Controller native AddLiquidity sidecar contract.

The Node sidecar's hand-rolled AddLiquidity IX (spec §9l, replaces the
Jupiter-swap proxy) commits us to two on-chain identifiers we must NEVER
drift on without an explicit Sanctum-protocol upgrade:

  - redemption_program = 5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx
    (S-Controller program; receipt-table verifier hits this address for
    Sanctum INF receipt confirmation.)
  - receipt_mint       = 5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm
    (INF SPL mint; balance-delta polled on user's ATA post-confirm.)

This test mocks the aiohttp `POST /build` round-trip from the Python
SolanaYieldBuilderAdapter to the Node sidecar (the JS adapter is not
import-able from Python) and asserts that whatever the sidecar emits as
`receiptMint` / `redemption_program` survives the model translation onto
the ExecutionStepV3.transaction object.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.solana_yield_builder import SolanaYieldBuilderAdapter


SANCTUM_PROGRAM = "5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx"
INF_MINT = "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    async def json(self) -> dict[str, Any]:
        return self._payload

    async def text(self) -> str:
        return str(self._payload)

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeSession:
    """Captures POST payloads + replays a canned sidecar response."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, json: dict[str, Any] | None = None) -> _FakeResponse:
        self.calls.append((url, json or {}))
        return _FakeResponse(self._payload)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_sanctum_native_addliquidity_step_pins_program_and_mint() -> None:
    """Sidecar AddLiquidity → ExecutionStepV3 must carry program + mint."""
    sidecar_payload: dict[str, Any] = {
        "transactions": [
            {
                "b64": "AQID",  # arbitrary base64 — the Python adapter doesn't decode it
                "summary": "Sanctum AddLiquidity 1 MSOL -> INF",
                "description": "hand-rolled disc=3 IX",
                "receiptToken": "INF",
                "receiptMint": INF_MINT,
                "redemption_program": SANCTUM_PROGRAM,
                "feeUsd": 0.01,
                "durationS": 20,
                "warnings": ["Native Sanctum AddLiquidity"],
            }
        ]
    }
    fake_session = _FakeSession(sidecar_payload)

    @asynccontextmanager
    async def _session_factory(*args: Any, **kwargs: Any):
        async with fake_session as s:
            yield s

    adapter = SolanaYieldBuilderAdapter()
    request = YieldBuildRequest(
        chain="solana",
        protocol="sanctum-infinity",
        asset_in="MSOL",
        amount_in=Decimal("1.0"),
        user_address="6n7Janary7xN2k5p4tFq3eYxs7eYzz9JdF3zPm9rE2yc",
        slippage_bps=50,
        extra={},
    )

    with patch("aiohttp.ClientSession", side_effect=_session_factory):
        steps = await adapter.build(request)

    assert len(steps) == 1, "Sanctum AddLiquidity must emit exactly one signable step."
    step = steps[0]
    assert step.transaction is not None, "Step must carry an unsigned solana transaction."
    assert step.transaction.serialized == "AQID"
    # The two non-negotiable receipt identifiers.
    assert getattr(step.transaction, "redemption_program", None) == SANCTUM_PROGRAM, (
        "Sanctum redemption_program must equal the S-Controller PROGRAM_ID; "
        "verifier + receipt-table both anchor on this address."
    )
    assert getattr(step.transaction, "receipt_mint", None) == INF_MINT, (
        "Sanctum receipt_mint must equal the INF SPL mint so the balance-delta "
        "verifier polls the right user ATA."
    )
    # Plumbing sanity — the sidecar saw exactly one /build call for sanctum.
    assert len(fake_session.calls) == 1
    url, body = fake_session.calls[0]
    assert url.endswith("/build")
    assert body.get("protocol") == "sanctum-infinity"
    assert body.get("asset") == "MSOL"
    assert body.get("amount") == "1.0"
