"""Integration test for WhaleTransactionStream.

Drives the service through its real message-handling pipeline using
synthetic `logsNotification` payloads — the same path production runs —
but mocks out the enrichment RPC call, the database, and the stream hub.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
from unittest.mock import AsyncMock, patch

import pytest

from src.data.solana_log_parser import DEX_PROGRAM_IDS, WSOL_MINT
from src.services.whale_stream import WhaleTransactionStream


def _pk_bytes(address: str) -> bytes:
    try:
        from solders.pubkey import Pubkey

        return bytes(Pubkey.from_string(address))
    except Exception:
        import base58

        return base58.b58decode(address)


def _anchor_disc(name: str) -> bytes:
    return hashlib.sha256(f"event:{name}".encode()).digest()[:8]


def _jupiter_swap_log(input_mint: str, input_amount: int, output_mint: str, output_amount: int) -> str:
    body = (
        b"\x00" * 32  # amm (irrelevant)
        + _pk_bytes(input_mint)
        + struct.pack("<Q", input_amount)
        + _pk_bytes(output_mint)
        + struct.pack("<Q", output_amount)
    )
    return "Program data: " + base64.b64encode(_anchor_disc("SwapEvent") + body).decode()


def _notification(sub_id: int, signature: str, logs: list[str], slot: int = 1000) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "subscription": sub_id,
            "result": {
                "context": {"slot": slot},
                "value": {
                    "signature": signature,
                    "err": None,
                    "logs": logs,
                },
            },
        },
    }


_TOKEN = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.insert_whale_transactions = AsyncMock(return_value=["sig-whale"])
    return db


@pytest.fixture
def mock_hub():
    hub = AsyncMock()
    hub.publish = AsyncMock()
    return hub


@pytest.fixture
def stream(mock_db, mock_hub):
    s = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)
    # Route subscription ID 1 to Jupiter for our test payloads.
    s._sub_to_dex[1] = "Jupiter"
    return s


@pytest.mark.asyncio
async def test_sub_threshold_swap_is_dropped_without_rpc_call(stream, mock_db):
    """A sub-threshold swap must never trigger enrichment (zero credit cost)."""
    # 10 SOL × $200 = $2,000 — below default $10K threshold.
    log = _jupiter_swap_log(WSOL_MINT, 10_000_000_000, _TOKEN, 1_000_000_000)
    notification = _notification(sub_id=1, signature="sig-small", logs=[log])

    with patch.object(stream, "_get_sol_price", AsyncMock(return_value=200.0)), \
         patch.object(stream, "_enrich_and_persist", AsyncMock()) as enrich:
        await stream._handle_message(json.dumps(notification))
        await asyncio.sleep(0)  # let any scheduled task run

    enrich.assert_not_called()
    mock_db.insert_whale_transactions.assert_not_called()


@pytest.mark.asyncio
async def test_whale_swap_triggers_enrichment(stream):
    """An above-threshold swap must be handed off to the enrichment path."""
    # 100 SOL × $200 = $20,000 — well above $10K.
    log = _jupiter_swap_log(WSOL_MINT, 100_000_000_000, _TOKEN, 8_200_000_000_000)
    notification = _notification(sub_id=1, signature="sig-whale", logs=[log])

    with patch.object(stream, "_get_sol_price", AsyncMock(return_value=200.0)), \
         patch.object(stream, "_enrich_and_persist", AsyncMock()) as enrich:
        await stream._handle_message(json.dumps(notification))
        # Give the scheduled task a tick to start.
        await asyncio.sleep(0)
        # Wait for background tasks created by _handle_message
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.wait(pending, timeout=1.0)

    assert enrich.call_count == 1
    # First positional arg is the SwapEvent
    swap_event = enrich.call_args.args[0]
    assert swap_event.signature == "sig-whale"
    assert swap_event.input_amount_raw == 100_000_000_000


@pytest.mark.asyncio
async def test_duplicate_signature_is_deduplicated(stream):
    log = _jupiter_swap_log(WSOL_MINT, 100_000_000_000, _TOKEN, 1)
    notification = _notification(sub_id=1, signature="sig-dup", logs=[log])

    with patch.object(stream, "_get_sol_price", AsyncMock(return_value=200.0)), \
         patch.object(stream, "_enrich_and_persist", AsyncMock()) as enrich:
        await stream._handle_message(json.dumps(notification))
        await stream._handle_message(json.dumps(notification))  # same sig twice
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.wait(pending, timeout=1.0)

    assert enrich.call_count == 1


@pytest.mark.asyncio
async def test_unknown_subscription_is_ignored(stream):
    log = _jupiter_swap_log(WSOL_MINT, 100_000_000_000, _TOKEN, 1)
    notification = _notification(sub_id=9999, signature="sig-x", logs=[log])

    with patch.object(stream, "_enrich_and_persist", AsyncMock()) as enrich:
        await stream._handle_message(json.dumps(notification))

    enrich.assert_not_called()


@pytest.mark.asyncio
async def test_failed_tx_is_ignored(stream):
    log = _jupiter_swap_log(WSOL_MINT, 100_000_000_000, _TOKEN, 1)
    notification = _notification(sub_id=1, signature="sig-err", logs=[log])
    notification["params"]["result"]["value"]["err"] = {"InstructionError": [0, "Custom"]}

    with patch.object(stream, "_enrich_and_persist", AsyncMock()) as enrich:
        await stream._handle_message(json.dumps(notification))

    enrich.assert_not_called()


@pytest.mark.asyncio
async def test_non_notification_messages_ignored(stream):
    subscribe_ack = {"jsonrpc": "2.0", "result": 42, "id": 1}
    with patch.object(stream, "_enrich_and_persist", AsyncMock()) as enrich:
        await stream._handle_message(json.dumps(subscribe_ack))
        await stream._handle_message("not-valid-json")
    enrich.assert_not_called()


@pytest.mark.asyncio
async def test_enrich_persists_and_broadcasts(stream, mock_db, mock_hub):
    """End-to-end enrichment with mocked RPC + mocked parser."""
    from src.data.solana_log_parser import SwapEvent

    event = SwapEvent(
        dex_name="Jupiter",
        signature="sig-e2e",
        slot=1,
        block_time=1_700_000_000,
        user_wallet=None,
        input_mint=WSOL_MINT,
        input_amount_raw=100_000_000_000,
        output_mint=_TOKEN,
        output_amount_raw=1,
        payment_side="input",
    )

    shaped = {
        "signature": "sig-e2e",
        "timestamp": 1_700_000_000,
        "type": "SWAP",
        "source": "JUPITER",
        "tokenTransfers": [],
        "nativeTransfers": [],
    }
    parsed_tx = {
        "signature": "sig-e2e",
        "wallet_address": "WalletX",
        "wallet_label": None,
        "token_address": _TOKEN,
        "token_symbol": "TKN",
        "token_name": "Token",
        "type": "buy",
        "amount_tokens": 1.0,
        "amount_usd": 20_000.0,
        "price_usd": 20_000.0,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "dex_name": "Jupiter",
    }

    with patch.object(stream, "_fetch_and_shape", AsyncMock(return_value=shaped)), \
         patch.object(stream, "_get_sol_price", AsyncMock(return_value=200.0)):
        # Reuse the existing SolanaClient parser; patch it to return our parsed_tx.
        from src.data.solana import SolanaClient
        with patch.object(
            SolanaClient, "_parse_helius_transaction", AsyncMock(return_value=parsed_tx)
        ):
            stream._solana_client = SolanaClient(rpc_url="http://unused", helius_api_key=None)
            await stream._enrich_and_persist(event, decoded_usd=20_000.0)

    mock_db.insert_whale_transactions.assert_awaited_once()
    inserted = mock_db.insert_whale_transactions.await_args.args[0]
    assert inserted[0]["signature"] == "sig-e2e"
    mock_hub.publish.assert_awaited_once()
    topic, payload = mock_hub.publish.await_args.args
    assert topic == "whale-transactions"
    assert payload["signature"] == "sig-e2e"
    assert payload["amount_usd"] == 20_000.0
    assert payload["dex_name"] == "Jupiter"


def test_dex_program_ids_cover_expected_dexes():
    for dex in [
        "Jupiter", "Raydium", "Raydium CLMM", "Raydium CP", "Pump.fun",
        "Orca", "Meteora", "Phoenix", "Lifinity",
    ]:
        assert dex in DEX_PROGRAM_IDS
