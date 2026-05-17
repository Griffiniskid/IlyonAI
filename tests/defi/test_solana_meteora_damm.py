"""Solana Meteora DAMM v2 + Dynamic Vault native adapter — pin test.

The Python `SolanaYieldBuilderAdapter` POSTs to the Node sidecar `/build`
endpoint. The new meteora.js adapter emits one of two native flows:

  * Mode A — DAMM v2 (extra.poolId): createPositionAndAddLiquidity, position
    NFT receipt, redemption_program = cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG
  * Mode B — Dynamic Vault (extra.vaultMint or extra.vaultTokenMint):
    VaultImpl.deposit, vault-share receipt, redemption_program =
    24Uqj9JCLxUeoC3hGfh5W3s9FM9uCHDS2SG3LYwBpyTi

These tests mock the sidecar response and assert the Python adapter
correctly surfaces `redemption_program` / `receipt_mint` on the
`UnsignedStepTransaction` via setattr, exactly like the Raydium pin tests.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.solana_yield_builder import SolanaYieldBuilderAdapter


DAMM_V2_PROGRAM = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
VAULT_PROGRAM = "24Uqj9JCLxUeoC3hGfh5W3s9FM9uCHDS2SG3LYwBpyTi"


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
        asset_in="USDC",
        amount_in=Decimal("100"),
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


def _damm_v2_response() -> dict[str, Any]:
    return {
        "transactions": [
            {
                "b64": "AQAA" + "A" * 200,
                "summary": "Meteora DAMM v2 createPositionAndAddLiquidity (USDC-SOL)",
                "description": f"DAMM v2 program {DAMM_V2_PROGRAM}. NFT receipt Pos1111...",
                "receiptToken": "meteora-position-nft",
                "receiptMint": "Pos1111111111111111111111111111111111111111",
                "position_nft": "Pos1111111111111111111111111111111111111111",
                "redemption_program": DAMM_V2_PROGRAM,
                "feeUsd": 0.02,
                "durationS": 30,
                "warnings": [
                    "Position is NFT-gated.",
                    "Transfer-hook Token-2022 mints unsupported on DAMM v2.",
                ],
                "simulation": {"ok": True, "benign": False, "unitsConsumed": 100000},
            }
        ]
    }


def _vault_response() -> dict[str, Any]:
    return {
        "transactions": [
            {
                "b64": "AQAA" + "A" * 200,
                "summary": "Meteora Dynamic Vault deposit 100 USDC",
                "description": f"Deposit via VAULT_PROGRAM {VAULT_PROGRAM}.",
                "receiptToken": "meteora-vault-share",
                "receiptMint": "VaultLp11111111111111111111111111111111111",
                "redemption_program": VAULT_PROGRAM,
                "feeUsd": 0.01,
                "durationS": 20,
                "warnings": [],
                "simulation": {"ok": True, "benign": False, "unitsConsumed": 100000},
            }
        ]
    }


def test_damm_v2_redemption_program_flows_through():
    """Mode A — DAMM v2 path: extra.poolId triggers cp-amm program id."""
    body = _damm_v2_response()
    adapter = SolanaYieldBuilderAdapter()
    request = _req(
        "meteora-damm-v2",
        extra={"poolId": "FakePoolDamm1111111111111111111111111111111"},
    )
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(request))

    assert len(steps) == 1
    step = steps[0]
    assert step.transaction is not None
    assert step.transaction.serialized.startswith("AQAA")
    # redemption_program must be the DAMM v2 cp-amm program id, stashed on
    # the tx via setattr by the Python adapter.
    assert getattr(step.transaction, "redemption_program", None) == DAMM_V2_PROGRAM
    # Position NFT receipt mint surfaced for the receipt table.
    assert getattr(step.transaction, "receipt_mint", None) == "Pos1111111111111111111111111111111111111111"


def test_dynamic_vault_redemption_program_flows_through():
    """Mode B — Dynamic Vault path: extra.vaultMint triggers vault program id."""
    body = _vault_response()
    adapter = SolanaYieldBuilderAdapter()
    request = _req(
        "meteora-vault",
        extra={"vaultMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},
    )
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(request))

    assert len(steps) == 1
    step = steps[0]
    assert step.transaction is not None
    assert getattr(step.transaction, "redemption_program", None) == VAULT_PROGRAM
    assert getattr(step.transaction, "receipt_mint", None) == "VaultLp11111111111111111111111111111111111"


@pytest.mark.parametrize(
    "alias",
    ["meteora", "meteora-dlmm", "meteora-vault"],
)
def test_meteora_aliases_supported(alias: str):
    """Sanity: meteora aliases must remain registered in the Python adapter's
    protocols set so supports() doesn't 404 the request before the sidecar
    even sees it. (DAMM v2-specific aliases like meteora-damm-v2 still route
    through this adapter via the "meteora" prefix family; the test asserts
    the already-registered aliases stay live.)"""
    adapter = SolanaYieldBuilderAdapter()
    cap = adapter.supports(chain="solana", protocol=alias, action="deposit")
    assert cap.supported, f"alias {alias} should be supported but: {cap.reason}"
