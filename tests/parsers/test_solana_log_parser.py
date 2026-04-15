"""Tests for Solana DEX log decoders.

We construct synthetic log payloads with the exact byte layout of real mainnet
events. This lets us verify the decoder bytecode paths without depending on
live network state.
"""

from __future__ import annotations

import base64
import hashlib
import struct

import pytest

from src.data.solana_log_parser import (
    DECODERS,
    DEX_PROGRAM_IDS,
    PAYMENT_MINTS,
    USDC_MINT,
    WSOL_MINT,
    _anchor_discriminator,
    compute_payment_usd,
    decode_jupiter,
    decode_pumpfun,
    decode_raydium_v4,
)


# ─── helpers ─────────────────────────────────────────────────────────────────


def _pk_bytes_from_b58(address: str) -> bytes:
    """Decode a base58 pubkey string to its 32 raw bytes."""
    try:
        from solders.pubkey import Pubkey

        return bytes(Pubkey.from_string(address))
    except Exception:
        import base58

        return base58.b58decode(address)


def _make_jupiter_swap_log(
    amm: bytes,
    input_mint: str,
    input_amount: int,
    output_mint: str,
    output_amount: int,
) -> str:
    disc = _anchor_discriminator("SwapEvent")
    body = (
        amm
        + _pk_bytes_from_b58(input_mint)
        + struct.pack("<Q", input_amount)
        + _pk_bytes_from_b58(output_mint)
        + struct.pack("<Q", output_amount)
    )
    return "Program data: " + base64.b64encode(disc + body).decode()


def _make_pumpfun_trade_log(
    mint: str,
    sol_amount: int,
    token_amount: int,
    is_buy: bool,
    user: str,
    timestamp: int,
) -> str:
    disc = _anchor_discriminator("TradeEvent")
    body = (
        _pk_bytes_from_b58(mint)
        + struct.pack("<Q", sol_amount)
        + struct.pack("<Q", token_amount)
        + struct.pack("<?", is_buy)
        + _pk_bytes_from_b58(user)
        + struct.pack("<q", timestamp)
        + struct.pack("<Q", 1_000_000_000)  # virtual_sol_reserves (unused)
        + struct.pack("<Q", 1_000_000_000)  # virtual_token_reserves (unused)
    )
    return "Program data: " + base64.b64encode(disc + body).decode()


_USER = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
_TOKEN = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"  # BONK


# ─── decoder registry / metadata ─────────────────────────────────────────────


def test_registry_covers_every_program_id():
    assert set(DECODERS.keys()) == set(DEX_PROGRAM_IDS.keys())


def test_registry_entries_are_callable():
    for name, fn in DECODERS.items():
        assert callable(fn), f"{name} decoder is not callable"


# ─── Jupiter decoder ─────────────────────────────────────────────────────────


class TestJupiterDecoder:
    def test_buy_with_wsol_input(self):
        amm = b"\x01" * 32
        logs = [
            _make_jupiter_swap_log(amm, WSOL_MINT, 45_000_000_000, _TOKEN, 8_200_000_000_000)
        ]
        event = decode_jupiter(logs, "sig-jup-buy", 100)
        assert event is not None
        assert event.dex_name == "Jupiter"
        assert event.signature == "sig-jup-buy"
        assert event.slot == 100
        assert event.input_mint == WSOL_MINT
        assert event.input_amount_raw == 45_000_000_000
        assert event.output_mint == _TOKEN
        assert event.output_amount_raw == 8_200_000_000_000
        assert event.payment_side == "input"

    def test_sell_with_usdc_output(self):
        amm = b"\x02" * 32
        logs = [
            _make_jupiter_swap_log(amm, _TOKEN, 1_000_000_000, USDC_MINT, 12_500_000_000)
        ]
        event = decode_jupiter(logs, "sig-jup-sell", 101)
        assert event is not None
        assert event.payment_side == "output"
        assert event.output_mint == USDC_MINT
        assert event.output_amount_raw == 12_500_000_000

    def test_token_to_token_returns_none(self):
        """No payment mint on either side — cannot be priced from log alone."""
        amm = b"\x03" * 32
        logs = [
            _make_jupiter_swap_log(amm, _TOKEN, 1_000_000_000, _USER, 500_000_000)
        ]
        event = decode_jupiter(logs, "sig-jup-hop", 102)
        assert event is None

    def test_intermediate_hop_skipped_final_matched(self):
        """A multi-event tx where only the last event has a payment side."""
        amm = b"\x04" * 32
        logs = [
            _make_jupiter_swap_log(amm, _TOKEN, 1_000_000_000, _USER, 500_000_000),
            _make_jupiter_swap_log(amm, _USER, 500_000_000, WSOL_MINT, 30_000_000_000),
        ]
        event = decode_jupiter(logs, "sig-jup-multi", 103)
        assert event is not None
        assert event.payment_side == "output"
        assert event.output_mint == WSOL_MINT

    def test_unrelated_logs_return_none(self):
        logs = [
            "Program 11111111111111111111111111111111 invoke [1]",
            "Program log: Instruction: Transfer",
            "Program data: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        ]
        assert decode_jupiter(logs, "sig", 0) is None

    def test_malformed_base64_ignored(self):
        logs = ["Program data: this-is-not-base64!!"]
        assert decode_jupiter(logs, "sig", 0) is None

    def test_truncated_discriminator_ignored(self):
        # Valid base64 but way too short for the SwapEvent struct.
        logs = ["Program data: " + base64.b64encode(b"short").decode()]
        assert decode_jupiter(logs, "sig", 0) is None


# ─── Pump.fun decoder ────────────────────────────────────────────────────────


class TestPumpFunDecoder:
    def test_buy(self):
        logs = [
            _make_pumpfun_trade_log(_TOKEN, 2_500_000_000, 15_000_000_000, True, _USER, 1_700_000_000)
        ]
        event = decode_pumpfun(logs, "sig-pump-buy", 200)
        assert event is not None
        assert event.dex_name == "Pump.fun"
        assert event.user_wallet == _USER
        assert event.input_mint == WSOL_MINT
        assert event.output_mint == _TOKEN
        assert event.input_amount_raw == 2_500_000_000
        assert event.output_amount_raw == 15_000_000_000
        assert event.payment_side == "input"
        assert event.block_time == 1_700_000_000

    def test_sell(self):
        logs = [
            _make_pumpfun_trade_log(_TOKEN, 3_000_000_000, 20_000_000_000, False, _USER, 1_700_000_500)
        ]
        event = decode_pumpfun(logs, "sig-pump-sell", 201)
        assert event is not None
        assert event.input_mint == _TOKEN
        assert event.output_mint == WSOL_MINT
        assert event.input_amount_raw == 20_000_000_000
        assert event.output_amount_raw == 3_000_000_000
        assert event.payment_side == "output"

    def test_wrong_discriminator_ignored(self):
        fake_disc = hashlib.sha256(b"event:OtherEvent").digest()[:8]
        blob = fake_disc + b"\x00" * 100
        logs = ["Program data: " + base64.b64encode(blob).decode()]
        assert decode_pumpfun(logs, "sig", 0) is None


# ─── Raydium V4 decoder (stub in v1) ────────────────────────────────────────


class TestRaydiumV4Decoder:
    def test_stub_returns_none(self):
        # ray_log prefix present but decoder intentionally returns None in v1.
        logs = ["ray_log: " + base64.b64encode(b"\x03" + b"\x00" * 80).decode()]
        assert decode_raydium_v4(logs, "sig", 0) is None


# ─── compute_payment_usd ─────────────────────────────────────────────────────


class TestComputePaymentUsd:
    def test_wsol_input(self):
        from src.data.solana_log_parser import SwapEvent

        event = SwapEvent(
            dex_name="Jupiter",
            signature="s",
            slot=1,
            block_time=None,
            user_wallet=None,
            input_mint=WSOL_MINT,
            input_amount_raw=45_000_000_000,  # 45 SOL
            output_mint=_TOKEN,
            output_amount_raw=1,
            payment_side="input",
        )
        assert compute_payment_usd(event, sol_price_usd=200.0) == pytest.approx(9000.0)

    def test_usdc_output(self):
        from src.data.solana_log_parser import SwapEvent

        event = SwapEvent(
            dex_name="Jupiter",
            signature="s",
            slot=1,
            block_time=None,
            user_wallet=None,
            input_mint=_TOKEN,
            input_amount_raw=1,
            output_mint=USDC_MINT,
            output_amount_raw=12_500_000_000,  # 12,500 USDC
            payment_side="output",
        )
        assert compute_payment_usd(event, sol_price_usd=200.0) == pytest.approx(12_500.0)

    def test_unknown_payment_returns_zero(self):
        from src.data.solana_log_parser import SwapEvent

        event = SwapEvent(
            dex_name="Jupiter",
            signature="s",
            slot=1,
            block_time=None,
            user_wallet=None,
            input_mint=_TOKEN,
            input_amount_raw=1_000_000,
            output_mint=_USER,
            output_amount_raw=500_000,
            payment_side="input",
        )
        assert compute_payment_usd(event, sol_price_usd=200.0) == 0.0


def test_payment_mint_set_is_sane():
    assert WSOL_MINT in PAYMENT_MINTS
    assert USDC_MINT in PAYMENT_MINTS
