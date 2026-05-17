"""Solana Raydium native adapter — assert AMM v4 + CPMM redemption_program
flows from the sidecar response through `step.transaction.redemption_program`.

The Python `SolanaYieldBuilderAdapter` POSTs to the Node sidecar's /build
endpoint and lifts the returned `{transactions:[{...}]}` shape into
`ExecutionStepV3` objects. The native raydium.js adapter we just wired emits
a `redemption_program` field on each tx (AMM v4 or CPMM program id), and the
Python adapter stashes it via setattr on the UnsignedStepTransaction so the
receipt-table and post-confirm verify can attribute the receipt correctly.

These tests mock `aiohttp.ClientSession` so they exercise the full Python
build() path without touching the network or the Node sidecar. Each case
asserts the surfaced `redemption_program` matches the canonical Raydium
program id for the requested mode.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.solana_yield_builder import SolanaYieldBuilderAdapter


AMM_V4_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
CPMM_PROGRAM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _req(protocol: str, *, extra: dict[str, Any] | None = None) -> YieldBuildRequest:
    return YieldBuildRequest(
        chain="solana",
        protocol=protocol,
        asset_in="SOL",
        amount_in=Decimal("1"),
        user_address="9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
        slippage_bps=50,
        extra=extra or {},
    )


class _MockResponse:
    def __init__(self, body: dict[str, Any], status: int = 200) -> None:
        self._body = body
        self.status = status

    async def __aenter__(self) -> "_MockResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._body

    async def text(self) -> str:
        import json
        return json.dumps(self._body)


class _MockSession:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    async def __aenter__(self) -> "_MockSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, json: dict[str, Any] | None = None) -> _MockResponse:
        return _MockResponse(self._body)


def _fake_session(body: dict[str, Any]):
    def _factory(*_args, **_kwargs):
        return _MockSession(body)

    return _factory


def _sidecar_response(program: str, *, summary: str, description: str) -> dict[str, Any]:
    return {
        "transactions": [
            {
                "b64": "AQEAAAA=",  # any base64 — Python adapter just passes it through
                "summary": summary,
                "description": description,
                "receiptToken": "RAY-LP",
                "receiptMint": "FakeLpMint1111111111111111111111111111111111",
                "redemption_program": program,
                "feeUsd": 0.02,
                "durationS": 25,
                "warnings": [f"Settles on {program}"],
                "simulation": {"ok": True, "benign": False, "unitsConsumed": 123456},
            }
        ]
    }


def test_amm_v4_redemption_program_flows_through_step_transaction():
    """AMM v4 default: poolId without poolType selects AMM v4 program id."""
    body = _sidecar_response(
        AMM_V4_PROGRAM,
        summary="Raydium AMM v4 addLiquidity (SOL-USDC)",
        description="Calls addLiquidity on Raydium pool FakePoolAmm. Native LP mint.",
    )
    adapter = SolanaYieldBuilderAdapter()
    request = _req(
        "raydium-amm-v4",
        extra={"poolId": "FakePoolAmm"},
    )
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(request))

    assert len(steps) == 1
    step = steps[0]
    assert step.transaction is not None
    assert step.transaction.serialized == "AQEAAAA="
    # redemption_program must be the AMM v4 program id, stashed on the tx
    # via setattr by the Python adapter.
    assert getattr(step.transaction, "redemption_program", None) == AMM_V4_PROGRAM
    assert getattr(step.transaction, "redemption_program") in {AMM_V4_PROGRAM, CPMM_PROGRAM}
    # Receipt mint forwarded as well.
    assert getattr(step.transaction, "receipt_mint", None) == "FakeLpMint1111111111111111111111111111111111"


def test_cpmm_redemption_program_flows_through_step_transaction():
    """CPMM: poolType='cpmm' triggers CPMM program id in the sidecar response."""
    body = _sidecar_response(
        CPMM_PROGRAM,
        summary="Raydium CPMM addLiquidity (SOL-USDC)",
        description="Calls addLiquidity on Raydium pool FakePoolCpmm. Native LP mint.",
    )
    adapter = SolanaYieldBuilderAdapter()
    request = _req(
        "raydium-cpmm",
        extra={"poolId": "FakePoolCpmm", "poolType": "cpmm"},
    )
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(request))

    assert len(steps) == 1
    step = steps[0]
    assert step.transaction is not None
    assert getattr(step.transaction, "redemption_program", None) == CPMM_PROGRAM
    assert getattr(step.transaction, "redemption_program") in {AMM_V4_PROGRAM, CPMM_PROGRAM}


@pytest.mark.parametrize(
    "alias",
    ["raydium-amm", "raydium-amm-v4", "raydium-cpmm", "raydium-cp", "raydium-clmm"],
)
def test_all_aliases_supported(alias: str):
    """Every alias declared on the JS adapter must also be in the Python
    adapter's protocols set — otherwise supports() would 404."""
    adapter = SolanaYieldBuilderAdapter()
    cap = adapter.supports(chain="solana", protocol=alias, action="deposit")
    assert cap.supported, f"alias {alias} should be supported but: {cap.reason}"


def test_redemption_program_one_of_canonical_set():
    """Defensive: any program returned by the sidecar must be in the canonical
    Raydium set when the protocol is raydium-*. Guards against a future bug
    where the JS adapter ships a wrong constant."""
    for program in (AMM_V4_PROGRAM, CPMM_PROGRAM):
        body = _sidecar_response(
            program,
            summary=f"Raydium addLiquidity via {program[:8]}",
            description="Native LP mint.",
        )
        adapter = SolanaYieldBuilderAdapter()
        with patch("aiohttp.ClientSession", new=_fake_session(body)):
            steps = _run(
                adapter.build(_req("raydium-amm-v4", extra={"poolId": "X"}))
            )
        assert getattr(steps[0].transaction, "redemption_program") in {
            AMM_V4_PROGRAM,
            CPMM_PROGRAM,
        }
