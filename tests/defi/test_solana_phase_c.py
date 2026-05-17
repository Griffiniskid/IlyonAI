"""Phase C Solana lifecycle close — sidecar contract tests.

Covers three close paths added to the Solana yield-builder sidecar:
  - Orca Whirlpool close_position    (orca.buildClose)
  - Kamino Lend withdraw              (kamino.buildWithdraw → buildUnstake)
  - Marinade order_unstake            (marinade.buildOrderUnstake)

The tests mock the sidecar HTTP response with a stub aiohttp ClientSession
context manager and assert the python SolanaYieldBuilderAdapter:

  1. Sends the correct `action` verb in the /build payload (dispatch routing).
  2. Surfaces the base64 transaction on the ExecutionStepV3.transaction.
  3. Propagates `redemption_program` (Whirlpool / Kamino-Lend / Marinade
     program IDs) onto step.transaction for receipt-reader attribution.

These are unit tests for the Python wrapper contract; the underlying Node SDK
calls are integration-tested by the sidecar's own jest harness + a live RPC.
"""
from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.solana_yield_builder import (
    SolanaYieldBuilderAdapter,
)


# Real on-chain program IDs — mainnet-verified, copied from the JS adapters.
WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
KAMINO_LEND_PROGRAM_ID = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD"
MARINADE_PROGRAM_ID = "MarBmsSgKXdrN1egZf5sqe1TMThczhMLJhYpaUm1cmRr"

# A throw-away but structurally valid base64 string for the assertion path —
# the python adapter doesn't decode it, only forwards it as serialized bytes.
_DUMMY_B64 = base64.b64encode(b"\x00" * 64).decode("ascii")

# A real-shaped Solana base58 pubkey (System Program — public knowledge).
_USER_PUBKEY = "11111111111111111111111111111111"
_POSITION_MINT = "POSiTionMintXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
_TICKET_PUBKEY = "TicKetAccount1xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


def _stub_session(captured: dict[str, Any], response_body: dict[str, Any], *, status: int = 200) -> MagicMock:
    """Build a MagicMock that mimics aiohttp.ClientSession's `async with` use.

    Captures the POST payload into `captured` and returns `response_body` from
    response.json(). Mirrors the pattern in tests/test_audit_database.py.
    """
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=response_body)
    response.text = AsyncMock(return_value=json.dumps(response_body))

    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=response)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    def _capture_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return post_cm

    session = MagicMock()
    session.post = MagicMock(side_effect=_capture_post)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_orca_close_position_round_trip():
    """Orca close_position: action verb dispatched + Whirlpool program id surfaced."""
    captured: dict[str, Any] = {}
    sidecar_response = {
        "transactions": [
            {
                "b64": _DUMMY_B64,
                "summary": "Orca close position POSiTion…",
                "description": "Decreases all liquidity, collects fees + rewards, closes NFT.",
                "receiptToken": "SOL",
                "redemption_program": WHIRLPOOL_PROGRAM_ID,
                "feeUsd": 0.01,
                "durationS": 30,
                "warnings": ["Closes entire position."],
                "simulation": {"ok": True, "benign": False, "unitsConsumed": 600_000},
            }
        ]
    }
    session = _stub_session(captured, sidecar_response)

    adapter = SolanaYieldBuilderAdapter()
    request = YieldBuildRequest(
        chain="solana",
        protocol="orca-whirlpools",
        asset_in="SOL",
        amount_in=Decimal("0"),  # close ignores amount
        user_address=_USER_PUBKEY,
        slippage_bps=100,
        extra={"action": "close_position", "positionMint": _POSITION_MINT},
    )

    with patch("aiohttp.ClientSession", return_value=session):
        steps = await adapter.build(request)

    # Payload dispatch — sidecar /build must receive action='close_position'.
    assert captured["json"]["action"] == "close_position"
    assert captured["json"]["protocol"] == "orca-whirlpools"
    assert captured["json"]["positionMint"] == _POSITION_MINT
    # extra is popped of action so the JS adapter sees only orchestration hints.
    assert "action" not in captured["json"]["extra"]

    # Step-level assertions: b64 forwarded + redemption_program stamped.
    assert len(steps) == 1
    step = steps[0]
    assert step.transaction is not None
    assert step.transaction.serialized == _DUMMY_B64
    assert getattr(step.transaction, "redemption_program", None) == WHIRLPOOL_PROGRAM_ID


@pytest.mark.asyncio
async def test_kamino_withdraw_round_trip():
    """Kamino withdraw: action='withdraw' dispatches to buildWithdraw + KLend program id."""
    captured: dict[str, Any] = {}
    sidecar_response = {
        "transactions": [
            {
                "b64": _DUMMY_B64,
                "summary": "Kamino withdraw 100 USDC",
                "description": "Direct Kamino vault withdraw via official REST.",
                "receiptToken": "USDC",
                "redemption_program": KAMINO_LEND_PROGRAM_ID,
                "feeUsd": 0.01,
                "durationS": 30,
                "warnings": [],
                "source": "kamino-rest",
                "simulation": {"ok": True, "benign": False, "unitsConsumed": 250_000},
            }
        ]
    }
    session = _stub_session(captured, sidecar_response)

    adapter = SolanaYieldBuilderAdapter()
    request = YieldBuildRequest(
        chain="solana",
        protocol="kamino-lend",
        asset_in="USDC",
        amount_in=Decimal("100"),
        user_address=_USER_PUBKEY,
        slippage_bps=50,
        extra={
            "action": "withdraw",
            "market": "DnReA1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "reserve": "RsRvA1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        },
    )

    with patch("aiohttp.ClientSession", return_value=session):
        steps = await adapter.build(request)

    assert captured["json"]["action"] == "withdraw"
    assert captured["json"]["protocol"] == "kamino-lend"
    # Market/reserve survive in extra for the JS adapter to forward to REST.
    assert captured["json"]["extra"]["market"].startswith("DnReA1")
    assert captured["json"]["extra"]["reserve"].startswith("RsRvA1")

    assert len(steps) == 1
    step = steps[0]
    assert step.transaction is not None
    assert step.transaction.serialized == _DUMMY_B64
    assert getattr(step.transaction, "redemption_program", None) == KAMINO_LEND_PROGRAM_ID


@pytest.mark.asyncio
async def test_marinade_order_unstake_round_trip():
    """Marinade order_unstake: ticket pubkey + lockup_end_ts + Marinade program id."""
    captured: dict[str, Any] = {}
    lockup_end = 1_900_000_000  # arbitrary future epoch
    sidecar_response = {
        "transactions": [
            {
                "b64": _DUMMY_B64,
                "summary": "Marinade order unstake 5 mSOL (next-epoch claim)",
                "description": "Burns mSOL + creates TicketAccount; claimable next epoch.",
                "receiptToken": "SOL",
                "redemption_program": MARINADE_PROGRAM_ID,
                "unstake_ticket": _TICKET_PUBKEY,
                "lockup_end_ts": lockup_end,
                "feeUsd": 0.005,
                "durationS": 15,
                "warnings": ["Delayed: claim after next epoch boundary."],
                "simulation": {"ok": True, "benign": False, "unitsConsumed": 80_000},
            }
        ]
    }
    session = _stub_session(captured, sidecar_response)

    adapter = SolanaYieldBuilderAdapter()
    request = YieldBuildRequest(
        chain="solana",
        protocol="marinade",
        asset_in="mSOL",
        amount_in=Decimal("5"),
        user_address=_USER_PUBKEY,
        slippage_bps=0,  # orderUnstake has no slippage — fixed exchange rate
        extra={"action": "order_unstake"},
    )

    with patch("aiohttp.ClientSession", return_value=session):
        steps = await adapter.build(request)

    assert captured["json"]["action"] == "order_unstake"
    assert captured["json"]["protocol"] == "marinade"
    assert captured["json"]["amount"] == "5"

    assert len(steps) == 1
    step = steps[0]
    assert step.transaction is not None
    assert step.transaction.serialized == _DUMMY_B64
    assert getattr(step.transaction, "redemption_program", None) == MARINADE_PROGRAM_ID
    # lockup_end_ts must flow through so the agent gates premature claim retries.
    assert getattr(step.transaction, "lockup_end_ts", None) == lockup_end
