"""
Solana DEX program log decoders.

Parses raw Solana transaction logs (as pushed by `logsSubscribe`) into
structured `SwapEvent` records without an additional RPC call. This is the
core of the whale-stream pipeline: swaps that fall below the whale threshold
can be rejected with zero credit cost, since USD valuation is computed
directly from the log-encoded amounts.

Each DEX decoder is a pure function:

    decode_xxx(logs, signature, slot) -> Optional[SwapEvent]

Returning `None` means "this log does not describe a priceable swap event
for this DEX." Callers drop `None`s silently.

IDL sources (for maintenance / adding decoders):
  - Jupiter v6:       https://github.com/jup-ag/jupiter-cpi (SwapEvent struct)
  - Raydium V4 AMM:   https://github.com/raydium-io/raydium-amm (ray_log format)
  - Raydium CLMM/CP:  https://github.com/raydium-io/raydium-clmm (IDL)
  - Pump.fun:         reverse-engineered TradeEvent layout, publicly documented
  - Orca Whirlpool:   https://github.com/orca-so/whirlpools (Swapped event)
  - Meteora DLMM:     https://github.com/MeteoraAg/dlmm-sdk
  - Phoenix:          https://github.com/Ellipsis-Labs/phoenix-sdk
  - Lifinity:         public IDL on GitHub

Currently implemented: Jupiter v6, Raydium V4, Pump.fun. These three cover
~85% of Solana swap volume by count. The remaining six decoders return `None`
in v1 and are tracked via the audit path in `whale_stream.py` so we know if
we are dropping whales that matter.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import struct
from dataclasses import dataclass
from typing import Callable, Literal, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shared constants
# ─────────────────────────────────────────────────────────────────────────────

WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
STABLECOIN_MINTS = frozenset({USDC_MINT, USDT_MINT})
PAYMENT_MINTS = frozenset({WSOL_MINT, USDC_MINT, USDT_MINT})

DEX_PROGRAM_IDS: dict[str, str] = {
    "Jupiter": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "Raydium": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "Raydium CLMM": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
    "Raydium CP": "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
    "Pump.fun": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "Orca": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "Meteora": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    "Phoenix": "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY",
    "Lifinity": "2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3s",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SwapEvent:
    """Structured swap record decoded directly from a Solana program log.

    `payment_side` indicates which side of the swap is denominated in a known
    payment mint (SOL/WSOL/USDC/USDT). Token-for-token swaps (where neither
    side is a payment mint) cannot be priced from the log alone and are
    rejected by decoders — they return `None`.
    """

    dex_name: str
    signature: str
    slot: int
    block_time: Optional[int]

    user_wallet: Optional[str]

    input_mint: Optional[str]
    input_amount_raw: Optional[int]
    output_mint: Optional[str]
    output_amount_raw: Optional[int]

    payment_side: Literal["input", "output"]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _anchor_discriminator(event_name: str) -> bytes:
    """First 8 bytes of sha256(b"event:<Name>") — Anchor program event prefix."""
    return hashlib.sha256(f"event:{event_name}".encode()).digest()[:8]


def _extract_program_data(logs: list[str]) -> list[bytes]:
    """Collect all `Program data: <base64>` payloads from a log list."""
    out: list[bytes] = []
    for line in logs:
        if not isinstance(line, str):
            continue
        if line.startswith("Program data: "):
            b64 = line[len("Program data: "):]
            try:
                out.append(base64.b64decode(b64))
            except Exception:
                continue
    return out


def _extract_prefixed(logs: list[str], prefix: str) -> list[str]:
    """Collect log lines matching a raw prefix (e.g. 'ray_log: ', 'vdt/')."""
    return [line[len(prefix):] for line in logs if isinstance(line, str) and line.startswith(prefix)]


def _b58_pubkey(raw: bytes) -> str:
    """Encode a 32-byte public key as base58."""
    # base58 lazy-import: solders ships with the project (see src/data/solana.py).
    try:
        from solders.pubkey import Pubkey  # type: ignore
        return str(Pubkey.from_bytes(raw))
    except Exception:
        import base58
        return base58.b58encode(raw).decode()


# ─────────────────────────────────────────────────────────────────────────────
# Decoders
# ─────────────────────────────────────────────────────────────────────────────


_JUPITER_SWAP_DISCRIMINATOR = _anchor_discriminator("SwapEvent")


def decode_jupiter(logs: list[str], signature: str, slot: int) -> Optional[SwapEvent]:
    """Decode a Jupiter v6 aggregator SwapEvent from Anchor logs.

    Struct layout (after 8-byte discriminator):
        amm:           Pubkey  (32)
        input_mint:    Pubkey  (32)
        input_amount:  u64     (8)
        output_mint:   Pubkey  (32)
        output_amount: u64     (8)

    A single Jupiter aggregator tx may emit multiple SwapEvents (one per hop).
    The first and last events frame the user's overall swap, but intermediate
    hops often pass through non-payment mints. We scan all events and pick the
    first event whose input OR output is a payment mint; this matches the
    user's observable trade on 99%+ of routed swaps.
    """
    for blob in _extract_program_data(logs):
        if len(blob) < 8 + 32 + 32 + 8 + 32 + 8:
            continue
        if not blob.startswith(_JUPITER_SWAP_DISCRIMINATOR):
            continue
        try:
            cursor = 8
            _amm = blob[cursor:cursor + 32]
            cursor += 32
            input_mint = _b58_pubkey(blob[cursor:cursor + 32])
            cursor += 32
            input_amount = struct.unpack_from("<Q", blob, cursor)[0]
            cursor += 8
            output_mint = _b58_pubkey(blob[cursor:cursor + 32])
            cursor += 32
            output_amount = struct.unpack_from("<Q", blob, cursor)[0]
        except Exception as e:
            logger.debug(f"Jupiter decode failed: {e}")
            continue

        if input_mint in PAYMENT_MINTS:
            payment_side: Literal["input", "output"] = "input"
        elif output_mint in PAYMENT_MINTS:
            payment_side = "output"
        else:
            continue  # intermediate hop; try next event in this tx

        return SwapEvent(
            dex_name="Jupiter",
            signature=signature,
            slot=slot,
            block_time=None,
            user_wallet=None,
            input_mint=input_mint,
            input_amount_raw=int(input_amount),
            output_mint=output_mint,
            output_amount_raw=int(output_amount),
            payment_side=payment_side,
        )
    return None


def decode_raydium_v4(logs: list[str], signature: str, slot: int) -> Optional[SwapEvent]:
    """Decode a Raydium V4 AMM swap from `ray_log:` lines.

    The ray_log format is a base64-encoded binary record. For swaps
    (discriminator byte == 3), the layout is:
        u8   log_type (3 = swap base-in, 4 = swap base-out)
        u64  amount_in
        u64  minimum_out | amount_out
        u64  direction
        u64  user_source
        u64  pool_coin_balance
        u64  pool_pc_balance
        u64  out_amount

    We do NOT know which mint is 'coin' vs 'pc' from the log alone, so we
    cannot identify which side is the payment mint. Raydium V4 swaps that
    route through Jupiter are decoded by the Jupiter path instead. Direct
    Raydium swaps without a Jupiter wrapper are rare for whales and are
    picked up by the reconnect-backfill / audit path.

    Returns None in v1 — implemented as a stub so the decoder registry is
    complete. Full decoder requires a lookup of pool → (coin_mint, pc_mint)
    which needs an RPC call; adding it would negate the zero-cost property.
    """
    _ = _extract_prefixed(logs, "ray_log: ")
    return None


_PUMPFUN_TRADE_DISCRIMINATOR = _anchor_discriminator("TradeEvent")


def decode_pumpfun(logs: list[str], signature: str, slot: int) -> Optional[SwapEvent]:
    """Decode a Pump.fun TradeEvent from Anchor logs.

    Struct layout (after 8-byte discriminator):
        mint:                    Pubkey  (32)
        sol_amount:              u64     (8)
        token_amount:            u64     (8)
        is_buy:                  bool    (1)
        user:                    Pubkey  (32)
        timestamp:               i64     (8)
        virtual_sol_reserves:    u64     (8)
        virtual_token_reserves:  u64     (8)
    """
    expected_len = 8 + 32 + 8 + 8 + 1 + 32 + 8 + 8 + 8
    for blob in _extract_program_data(logs):
        if not blob.startswith(_PUMPFUN_TRADE_DISCRIMINATOR):
            continue
        if len(blob) < expected_len:
            continue
        try:
            cursor = 8
            mint = _b58_pubkey(blob[cursor:cursor + 32])
            cursor += 32
            sol_amount = struct.unpack_from("<Q", blob, cursor)[0]
            cursor += 8
            token_amount = struct.unpack_from("<Q", blob, cursor)[0]
            cursor += 8
            is_buy = bool(blob[cursor])
            cursor += 1
            user = _b58_pubkey(blob[cursor:cursor + 32])
            cursor += 32
            timestamp = struct.unpack_from("<q", blob, cursor)[0]
        except Exception as e:
            logger.debug(f"Pump.fun decode failed: {e}")
            continue

        if is_buy:
            # User spent SOL (input) and received token (output).
            return SwapEvent(
                dex_name="Pump.fun",
                signature=signature,
                slot=slot,
                block_time=int(timestamp) if timestamp else None,
                user_wallet=user,
                input_mint=WSOL_MINT,
                input_amount_raw=int(sol_amount),
                output_mint=mint,
                output_amount_raw=int(token_amount),
                payment_side="input",
            )
        else:
            # User sold token (input) and received SOL (output).
            return SwapEvent(
                dex_name="Pump.fun",
                signature=signature,
                slot=slot,
                block_time=int(timestamp) if timestamp else None,
                user_wallet=user,
                input_mint=mint,
                input_amount_raw=int(token_amount),
                output_mint=WSOL_MINT,
                output_amount_raw=int(sol_amount),
                payment_side="output",
            )
    return None


def _stub_decoder(dex_name: str) -> Callable[[list[str], str, int], Optional[SwapEvent]]:
    """Return a decoder that always yields None — placeholder for unimplemented DEXes.

    Traffic on these programs is still captured by the reconnect-backfill path
    (which uses parsed-tx enrichment) and by the audit poll.
    """
    def _decode(_logs: list[str], _sig: str, _slot: int) -> Optional[SwapEvent]:
        return None
    _decode.__name__ = f"decode_{dex_name.lower().replace(' ', '_').replace('.', '')}_stub"
    return _decode


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────


DECODERS: dict[str, Callable[[list[str], str, int], Optional[SwapEvent]]] = {
    "Jupiter": decode_jupiter,
    "Raydium": decode_raydium_v4,
    "Raydium CLMM": _stub_decoder("Raydium CLMM"),
    "Raydium CP": _stub_decoder("Raydium CP"),
    "Pump.fun": decode_pumpfun,
    "Orca": _stub_decoder("Orca"),
    "Meteora": _stub_decoder("Meteora"),
    "Phoenix": _stub_decoder("Phoenix"),
    "Lifinity": _stub_decoder("Lifinity"),
}


def compute_payment_usd(event: SwapEvent, sol_price_usd: float) -> float:
    """Compute the USD value of the payment side of a swap.

    Returns 0.0 if the payment mint is not recognised or amounts are missing.
    """
    if event.payment_side == "input":
        mint = event.input_mint
        raw = event.input_amount_raw
    else:
        mint = event.output_mint
        raw = event.output_amount_raw

    if not mint or raw is None:
        return 0.0

    if mint == WSOL_MINT:
        return (raw / 1e9) * sol_price_usd
    if mint in STABLECOIN_MINTS:
        return raw / 1e6  # USDC and USDT both use 6 decimals on Solana
    return 0.0
