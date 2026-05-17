"""Solana JLP (Jupiter Perpetuals LP) native adapter pin test — Phase B.1.

Asserts the native `add_liquidity2` adapter's receipt-side metadata
(receiptMint / redemption_program / lockup_end_ts / underlying_custody)
flows from the Node sidecar JSON response through the Python adapter and
lands on `step.transaction` as setattr-stashed attributes.

Why this matters:
  - receipt_mint pins the SPL mint the wallet balance-deltas after sign
    (JLP mint = 27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4).
  - redemption_program tells post-confirm verify which on-chain program
    minted the receipt (Jupiter Perpetuals = PERPHjGBqRH…).
  - lockup_end_ts gates unstake retries — the runtime won't broadcast a
    withdraw before this timestamp because the program will revert.
  - underlying_custody attributes the deposit to the per-asset custody
    (SOL / ETH / BTC / USDC / USDT) so receipt audit can confirm the
    exact asset path.

Mocks aiohttp.ClientSession so the test never touches the Node sidecar or
the network — same isolation pattern used by test_solana_raydium.py.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.solana_yield_builder import SolanaYieldBuilderAdapter


JLP_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"
JLP_PROGRAM = "PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu"
SOL_CUSTODY = "7xS2gz2bTp3fwCC7knJvUWTEU9Tycczu6VhJYKgi1wdz"
USDC_CUSTODY = "G18jKKXQwBbrHeiK3C9MRXhkHsLHf7XgCSisykV46EZa"
ETH_CUSTODY = "AQCGyheWPLeo6Qp9WpYS9m3Qj479t7R636N9ey1rEjEn"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _req(protocol: str, *, asset: str = "USDC", extra: dict[str, Any] | None = None) -> YieldBuildRequest:
    return YieldBuildRequest(
        chain="solana",
        protocol=protocol,
        asset_in=asset,
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


def _jlp_sidecar_response(
    *,
    asset_sym: str,
    custody: str,
    lockup_end_ts: int = 1_900_000_000,
) -> dict[str, Any]:
    return {
        "transactions": [
            {
                "b64": "AQEAAAA=",  # opaque base64 — Python passes through verbatim
                "summary": f"JLP native add_liquidity2: 100 {asset_sym} → JLP",
                "description": (
                    f"Calls Jupiter Perpetuals add_liquidity2 on program {JLP_PROGRAM} "
                    f"with the {asset_sym} custody ({custody}). Native NAV mint."
                ),
                "receiptToken": "JLP",
                "receiptMint": JLP_MINT,
                "redemption_program": JLP_PROGRAM,
                "lockup_end_ts": lockup_end_ts,
                "underlying_custody": custody,
                "feeUsd": 0.01,
                "durationS": 20,
                "warnings": [
                    "Native JLP mint via add_liquidity2.",
                    "1-hour withdraw lockup begins at deposit confirmation.",
                ],
                "simulation": {"ok": True, "benign": False, "unitsConsumed": 124000},
            }
        ]
    }


def test_jlp_receipt_mint_flows_through_step_transaction():
    body = _jlp_sidecar_response(asset_sym="USDC", custody=USDC_CUSTODY)
    adapter = SolanaYieldBuilderAdapter()
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(_req("jlp", asset="USDC")))
    assert len(steps) == 1
    step = steps[0]
    assert step.transaction is not None
    assert step.transaction.serialized == "AQEAAAA="
    assert getattr(step.transaction, "receipt_mint", None) == JLP_MINT


def test_jlp_redemption_program_flows_through_step_transaction():
    body = _jlp_sidecar_response(asset_sym="USDC", custody=USDC_CUSTODY)
    adapter = SolanaYieldBuilderAdapter()
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(_req("jupiter-perpetuals", asset="USDC")))
    step = steps[0]
    assert getattr(step.transaction, "redemption_program", None) == JLP_PROGRAM


def test_jlp_lockup_end_ts_flows_through_step_transaction():
    """1-hour lockup ts must reach the step so the runtime can gate retries."""
    body = _jlp_sidecar_response(
        asset_sym="USDC", custody=USDC_CUSTODY, lockup_end_ts=1_900_000_999,
    )
    adapter = SolanaYieldBuilderAdapter()
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(_req("jlp", asset="USDC")))
    step = steps[0]
    assert getattr(step.transaction, "lockup_end_ts", None) == 1_900_000_999


def test_jlp_underlying_custody_flows_through_step_transaction_sol():
    body = _jlp_sidecar_response(asset_sym="SOL", custody=SOL_CUSTODY)
    adapter = SolanaYieldBuilderAdapter()
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(_req("jlp", asset="SOL")))
    step = steps[0]
    assert getattr(step.transaction, "underlying_custody", None) == SOL_CUSTODY


def test_jlp_underlying_custody_flows_through_step_transaction_eth():
    body = _jlp_sidecar_response(asset_sym="ETH", custody=ETH_CUSTODY)
    adapter = SolanaYieldBuilderAdapter()
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(_req("jlp", asset="ETH")))
    step = steps[0]
    assert getattr(step.transaction, "underlying_custody", None) == ETH_CUSTODY


def test_jlp_all_four_fields_present_together():
    """All four native-IX fields must flow on a single build call."""
    body = _jlp_sidecar_response(asset_sym="USDC", custody=USDC_CUSTODY)
    adapter = SolanaYieldBuilderAdapter()
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(_req("jlp", asset="USDC")))
    step = steps[0]
    tx = step.transaction
    assert getattr(tx, "receipt_mint", None) == JLP_MINT
    assert getattr(tx, "redemption_program", None) == JLP_PROGRAM
    assert getattr(tx, "lockup_end_ts", None) is not None
    assert getattr(tx, "underlying_custody", None) == USDC_CUSTODY


@pytest.mark.parametrize(
    "alias",
    ["jlp", "jupiter-perps", "jupiter-perpetuals", "jupiter-perpetuals-lp"],
)
def test_jlp_aliases_supported(alias: str):
    """Every JS-adapter alias must be in the Python protocols frozenset."""
    adapter = SolanaYieldBuilderAdapter()
    cap = adapter.supports(chain="solana", protocol=alias, action="deposit")
    assert cap.supported, f"alias {alias} should be supported but: {cap.reason}"


def test_jlp_camelcase_keys_also_flow():
    """Defensive: sidecar may emit camelCase variants — both must flow."""
    body = {
        "transactions": [
            {
                "b64": "AQEAAAA=",
                "summary": "JLP camelCase variant",
                "description": "test",
                "receiptToken": "JLP",
                "receiptMint": JLP_MINT,
                "redemptionProgram": JLP_PROGRAM,
                "lockupEndTs": 1_900_000_111,
                "underlyingCustody": USDC_CUSTODY,
                "feeUsd": 0.01,
                "durationS": 20,
                "warnings": [],
                "simulation": {"ok": True, "benign": False, "unitsConsumed": 100000},
            }
        ]
    }
    adapter = SolanaYieldBuilderAdapter()
    with patch("aiohttp.ClientSession", new=_fake_session(body)):
        steps = _run(adapter.build(_req("jlp", asset="USDC")))
    tx = steps[0].transaction
    assert getattr(tx, "receipt_mint", None) == JLP_MINT
    assert getattr(tx, "redemption_program", None) == JLP_PROGRAM
    assert getattr(tx, "lockup_end_ts", None) == 1_900_000_111
    assert getattr(tx, "underlying_custody", None) == USDC_CUSTODY
