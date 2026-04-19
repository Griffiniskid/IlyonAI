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


# ─── Amount-only decoder → enrichment path ─────────────────────────────────


_POOL = "HxuoT6xqsC8N71tf9Li7KzB4QQ4YjvG29q3mUfxKmiyM"


def _anchor_event_log(event_name: str, payload: bytes) -> str:
    disc = hashlib.sha256(f"event:{event_name}".encode()).digest()[:8]
    return "Program data: " + base64.b64encode(disc + payload).decode()


def _raydium_clmm_payload(pool: str, amount_0: int, amount_1: int) -> bytes:
    """pool_state(32) sender(32) ta0(32) ta1(32)
       amount_0(u64) fee_0(u64) amount_1(u64) fee_1(u64) zero_for_one(bool)..."""
    body = (
        _pk_bytes(pool)
        + b"\x00" * 32 * 3
        + struct.pack("<Q", amount_0)
        + struct.pack("<Q", 0)  # fee_0
        + struct.pack("<Q", amount_1)
        + struct.pack("<Q", 0)  # fee_1
        + b"\x00"               # zero_for_one
        + b"\x00" * 16          # sqrt_price_x64
        + b"\x00" * 16          # liquidity
        + b"\x00" * 4           # tick
    )
    return body


@pytest.mark.asyncio
async def test_amount_only_event_above_threshold_triggers_enrichment(mock_db, mock_hub):
    """Raydium CLMM SwapEvent over the coarse raw threshold must reach enrichment."""
    stream = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)
    stream._sub_to_dex[7] = "Raydium CLMM"

    # 10^11 raw on either side is well above AMOUNT_ONLY_WHALE_CANDIDATE_RAW (5e9).
    log = _anchor_event_log("SwapEvent", _raydium_clmm_payload(_POOL, 10**11, 5 * 10**11))
    notification = _notification(sub_id=7, signature="sig-clmm-big", logs=[log])

    with patch.object(stream, "_enrich_and_persist", AsyncMock()) as enrich:
        await stream._handle_message(json.dumps(notification))
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.wait(pending, timeout=1.0)

    assert enrich.call_count == 1
    event = enrich.call_args.args[0]
    assert event.dex_name == "Raydium CLMM"
    # Amount-only events carry no mint/payment_side.
    assert event.payment_side is None
    assert event.input_mint is None
    assert event.pool_address == _POOL


@pytest.mark.asyncio
async def test_amount_only_event_below_threshold_is_dropped(mock_db, mock_hub):
    """Raydium CLMM SwapEvent below the coarse raw threshold must NOT enrich."""
    stream = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)
    stream._sub_to_dex[7] = "Raydium CLMM"

    # Both amounts 10^8 — well below AMOUNT_ONLY_WHALE_CANDIDATE_RAW (5e9).
    log = _anchor_event_log("SwapEvent", _raydium_clmm_payload(_POOL, 10**8, 10**8))
    notification = _notification(sub_id=7, signature="sig-clmm-small", logs=[log])

    with patch.object(stream, "_enrich_and_persist", AsyncMock()) as enrich:
        await stream._handle_message(json.dumps(notification))
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.wait(pending, timeout=1.0)

    enrich.assert_not_called()


# ─── RPC poll path (replaces parsed-tx endpoint) ────────────────────────────


@pytest.mark.asyncio
async def test_rpc_poll_uses_standard_rpc_not_parsed_tx_endpoint(mock_db, mock_hub):
    """The RPC poll must hit only /?api-key=... (standard RPC); never /v0/addresses."""
    stream = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)
    from src.data.solana import SolanaClient
    stream._solana_client = SolanaClient(rpc_url="http://unused", helius_api_key=None)

    # Capture signatures requested and stub enrichment.
    with patch.object(stream, "_get_signatures_for_address",
                      AsyncMock(return_value=[])) as get_sigs, \
         patch.object(stream, "_fetch_and_shape_signature",
                      AsyncMock(return_value=None)), \
         patch("src.services.whale_stream.settings") as mock_settings:
        mock_settings.helius_api_key = "test-key"
        mock_settings.min_whale_usd = 10_000.0
        new_count = await stream._rpc_poll_all_dexes(source="test")

    assert new_count == 0
    # One call per DEX program id.
    assert get_sigs.await_count == len(DEX_PROGRAM_IDS)
    # Ensure none of the call URLs are the parsed-tx endpoint.
    for call in get_sigs.await_args_list:
        # `address` kwarg or second positional should be a DEX program ID string.
        kwargs = call.kwargs
        address = kwargs.get("address")
        assert isinstance(address, str)
        assert address in DEX_PROGRAM_IDS.values()


@pytest.mark.asyncio
async def test_enrich_token_metadata_resolves_from_dexscreener(mock_db, mock_hub):
    """A tx with '???' symbol must be resolved via DexScreener and cached."""
    stream = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)

    mint = _TOKEN
    parsed_txs = [
        {"token_address": mint, "token_symbol": "???", "token_name": "Unknown"},
        {"token_address": mint, "token_symbol": "???", "token_name": "Unknown"},  # dup mint
    ]

    class FakeDex:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get_token(self, addr):
            assert addr == mint
            return {"main": {"baseToken": {"address": addr, "symbol": "BONK", "name": "Bonk"}}}

    with patch("src.data.dexscreener.DexScreenerClient", FakeDex):
        await stream._enrich_token_metadata(parsed_txs)

    assert parsed_txs[0]["token_symbol"] == "BONK"
    assert parsed_txs[0]["token_name"] == "Bonk"
    # Cache should contain the mint.
    assert mint in stream._token_meta_cache

    # Second call hits the cache (no new HTTP).
    parsed_txs2 = [{"token_address": mint, "token_symbol": "???", "token_name": "Unknown"}]
    with patch("src.data.dexscreener.DexScreenerClient") as mock_client:
        await stream._enrich_token_metadata(parsed_txs2)
    mock_client.assert_not_called()
    assert parsed_txs2[0]["token_symbol"] == "BONK"


@pytest.mark.asyncio
async def test_backfill_resolves_legacy_placeholder_rows(mock_db, mock_hub):
    """The DB backfill must update rows stuck with token_symbol='???'."""
    stream = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)

    mint = _TOKEN
    mock_db.get_whale_unresolved_token_addresses = AsyncMock(return_value=[mint])
    mock_db.update_whale_token_metadata = AsyncMock(return_value=3)

    class FakeDex:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get_token(self, addr):
            return {"main": {"baseToken": {"address": addr, "symbol": "WIF", "name": "dogwifhat"}}}

    with patch("src.data.dexscreener.DexScreenerClient", FakeDex):
        updated = await stream._backfill_unresolved_token_symbols()

    assert updated == 3
    mock_db.update_whale_token_metadata.assert_awaited_once()
    kwargs = mock_db.update_whale_token_metadata.await_args.kwargs
    assert kwargs["token_address"] == mint
    assert kwargs["symbol"] == "WIF"
    assert kwargs["name"] == "dogwifhat"


@pytest.mark.asyncio
async def test_rpc_poll_persists_whale_and_broadcasts(mock_db, mock_hub):
    """End-to-end RPC poll: a new whale sig yields DB insert + broadcast."""
    stream = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)
    from src.data.solana import SolanaClient
    stream._solana_client = SolanaClient(rpc_url="http://unused", helius_api_key=None)

    shaped = {
        "signature": "rpc-sig-1",
        "timestamp": 1_700_000_000,
        "type": "SWAP",
        "source": "ORCA",
        "tokenTransfers": [],
        "nativeTransfers": [],
    }
    parsed_tx = {
        "signature": "rpc-sig-1",
        "wallet_address": "WalletRPC",
        "wallet_label": None,
        "token_address": _TOKEN,
        "token_symbol": "TKN",
        "token_name": "Token",
        "type": "buy",
        "amount_tokens": 1.0,
        "amount_usd": 25_000.0,
        "price_usd": 25_000.0,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "dex_name": "Orca",
    }
    mock_db.insert_whale_transactions = AsyncMock(return_value=["rpc-sig-1"])

    async def sigs_side_effect(session, address, limit=100, until=None):
        if address == DEX_PROGRAM_IDS["Orca"]:
            return ["rpc-sig-1"]
        return []

    with patch.object(stream, "_get_signatures_for_address", AsyncMock(side_effect=sigs_side_effect)), \
         patch.object(stream, "_fetch_and_shape_signature", AsyncMock(return_value=shaped)), \
         patch.object(stream, "_get_sol_price", AsyncMock(return_value=200.0)), \
         patch("src.services.whale_stream.settings") as mock_settings, \
         patch.object(SolanaClient, "_parse_helius_transaction",
                      AsyncMock(return_value=parsed_tx)):
        mock_settings.helius_api_key = "test-key"
        mock_settings.min_whale_usd = 10_000.0
        new_count = await stream._rpc_poll_all_dexes(source="test")

    assert new_count == 1
    mock_db.insert_whale_transactions.assert_awaited_once()
    mock_hub.publish.assert_awaited_once()
    topic, payload = mock_hub.publish.await_args.args
    assert topic == "whale-transactions"
    assert payload["signature"] == "rpc-sig-1"
    assert payload["amount_usd"] == 25_000.0


# ─── Alpha-token filter ─────────────────────────────────────────────────────


def test_token_filter_blocks_stablecoins_and_majors():
    from src.data.token_filters import is_alpha_token, EXCLUDED_MINTS

    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    WBTC = "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh"

    # Mint-level
    assert USDC in EXCLUDED_MINTS
    assert USDT in EXCLUDED_MINTS
    assert WBTC in EXCLUDED_MINTS
    assert not is_alpha_token(USDC, "USDC")
    assert not is_alpha_token(WBTC, "wBTC")

    # Symbol-level (unknown mint, excluded symbol)
    assert not is_alpha_token("SomeRandomMint", "USDC")
    assert not is_alpha_token("SomeRandomMint", "wETH")
    assert not is_alpha_token("SomeRandomMint", "TRX")
    assert not is_alpha_token("SomeRandomMint", "jitoSOL")
    assert not is_alpha_token("SomeRandomMint", "PYUSD")

    # Legitimate memecoin passes through
    assert is_alpha_token(_TOKEN, "BONK")
    assert is_alpha_token(_TOKEN, "WIF")
    # '???' (placeholder) must not be blocked at the symbol layer.
    assert is_alpha_token(_TOKEN, "???")


@pytest.mark.asyncio
async def test_rpc_poll_drops_non_alpha_tokens_after_enrichment(mock_db, mock_hub):
    """Even if parser returns a tx, post-enrichment filter must drop stablecoins."""
    stream = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)
    from src.data.solana import SolanaClient
    stream._solana_client = SolanaClient(rpc_url="http://unused", helius_api_key=None)

    shaped = {
        "signature": "sig-stable",
        "timestamp": 1_700_000_000,
        "type": "SWAP",
        "source": "ORCA",
        "tokenTransfers": [],
        "nativeTransfers": [],
    }
    # Simulate parser returning a USDC transaction (shouldn't reach DB).
    usdc_parsed = {
        "signature": "sig-stable",
        "wallet_address": "WalletX",
        "wallet_label": None,
        "token_address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "token_symbol": "USDC",
        "token_name": "USD Coin",
        "type": "buy",
        "amount_tokens": 50_000.0,
        "amount_usd": 50_000.0,
        "price_usd": 1.0,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "dex_name": "Orca",
    }

    async def sigs_side_effect(session, address, limit=100, until=None):
        if address == DEX_PROGRAM_IDS["Orca"]:
            return ["sig-stable"]
        return []

    with patch.object(stream, "_get_signatures_for_address", AsyncMock(side_effect=sigs_side_effect)), \
         patch.object(stream, "_fetch_and_shape_signature", AsyncMock(return_value=shaped)), \
         patch.object(stream, "_get_sol_price", AsyncMock(return_value=200.0)), \
         patch.object(stream, "_enrich_token_metadata", AsyncMock()), \
         patch("src.services.whale_stream.settings") as mock_settings, \
         patch.object(SolanaClient, "_parse_helius_transaction",
                      AsyncMock(return_value=usdc_parsed)):
        mock_settings.helius_api_key = "test-key"
        mock_settings.min_whale_usd = 10_000.0
        new_count = await stream._rpc_poll_all_dexes(source="test")

    assert new_count == 0
    mock_db.insert_whale_transactions.assert_not_called()
    mock_hub.publish.assert_not_called()


@pytest.mark.asyncio
async def test_enrich_and_persist_drops_non_alpha_after_metadata(mock_db, mock_hub):
    """Live WS enrichment must drop txs that resolve to an excluded symbol."""
    from src.data.solana_log_parser import SwapEvent

    stream = WhaleTransactionStream(db=mock_db, stream_hub=mock_hub)

    event = SwapEvent(
        dex_name="Jupiter",
        signature="sig-bridged",
        slot=1,
        block_time=1_700_000_000,
        user_wallet=None,
        input_mint=WSOL_MINT,
        input_amount_raw=100_000_000_000,
        output_mint=_TOKEN,
        output_amount_raw=1,
        payment_side="input",
    )

    shaped = {"signature": "sig-bridged", "timestamp": 1_700_000_000,
              "type": "SWAP", "source": "JUPITER",
              "tokenTransfers": [], "nativeTransfers": []}
    # Parser returns a tx whose post-enrichment symbol becomes TRX.
    trx_parsed = {
        "signature": "sig-bridged",
        "wallet_address": "WalletX",
        "wallet_label": None,
        "token_address": "UnknownMintAddress",
        "token_symbol": "TRX",
        "token_name": "Tron",
        "type": "buy",
        "amount_tokens": 1.0,
        "amount_usd": 20_000.0,
        "price_usd": 20_000.0,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "dex_name": "Jupiter",
    }

    from src.data.solana import SolanaClient
    with patch.object(stream, "_fetch_and_shape", AsyncMock(return_value=shaped)), \
         patch.object(stream, "_get_sol_price", AsyncMock(return_value=200.0)), \
         patch.object(stream, "_enrich_token_metadata", AsyncMock()), \
         patch.object(SolanaClient, "_parse_helius_transaction",
                      AsyncMock(return_value=trx_parsed)):
        stream._solana_client = SolanaClient(rpc_url="http://unused", helius_api_key=None)
        await stream._enrich_and_persist(event, decoded_usd=20_000.0)

    mock_db.insert_whale_transactions.assert_not_called()
    mock_hub.publish.assert_not_called()
