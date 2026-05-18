"""Tests for SPL receipt verification paths in receipt_reader.py.

Covers the four SPL receipt kinds now wired into `verify_receipt`:
  - MSOL (Marinade mSOL SPL token)
  - JITOSOL (Jito jitoSOL SPL token)
  - JLP (Jupiter Perpetuals LP SPL token)
  - POSITION_PDA / POSITION_PDA_WITH_NFT (Meteora DLMM / Whirlpool / Raydium CLMM)

All Solana RPC calls are stubbed via monkeypatch — no live network.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

import src.defi.verification.receipt_reader as reader_mod
from src.defi.verification.receipt_reader import (
    _JITOSOL_MINT,
    _JLP_MINT,
    _MSOL_MINT,
    ReadResult,
    verify_receipt,
)
from src.defi.verification.receipt_table import ReceiptKind


_OWNER = "9xQeWvG816bUx9EPa2qsB7nNg7c6X6CzsLcsv6q9MjP2"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _stub_token_balance(monkeypatch, *, by_mint: dict[str, tuple[int | None, int | None]]):
    """Stub `_spl_token_balance` to return per-mint synthetic balances.

    `by_mint` maps mint string -> (raw_amount, decimals).
    """
    async def _fake(owner: str, mint: str, *, rpc_url: str | None = None,
                    session: Any = None) -> tuple[int | None, int | None]:
        return by_mint.get(mint, (0, 9))

    monkeypatch.setattr(reader_mod, "_spl_token_balance", _fake)


def _stub_account_exists(monkeypatch, *, exists: bool, account: dict | None = None):
    async def _fake(address: str, *, rpc_url: str | None = None,
                    session: Any = None) -> tuple[bool, dict | None]:
        return (exists, account)

    monkeypatch.setattr(reader_mod, "_solana_account_exists", _fake)


# ─── MSOL ────────────────────────────────────────────────────────────────────

def test_msol_confirmed_when_balance_positive(monkeypatch):
    _stub_token_balance(monkeypatch, by_mint={_MSOL_MINT: (5_000_000_000, 9)})
    r = _run(verify_receipt(
        kind=ReceiptKind.MSOL, chain="solana", owner=_OWNER, expected={},
    ))
    assert isinstance(r, ReadResult)
    assert r.confirmed is True, r.detail
    assert r.raw["balance"] == 5_000_000_000
    assert r.raw["mint"] == _MSOL_MINT


def test_msol_rejected_when_balance_zero(monkeypatch):
    _stub_token_balance(monkeypatch, by_mint={_MSOL_MINT: (0, 9)})
    r = _run(verify_receipt(
        kind=ReceiptKind.MSOL, chain="solana", owner=_OWNER, expected={},
    ))
    assert r.confirmed is False
    assert "< 1" in r.detail


def test_msol_rpc_unavailable_does_not_fabricate_confirmation(monkeypatch):
    # transport flake -> balance=None -> verifier must refuse to confirm.
    _stub_token_balance(monkeypatch, by_mint={_MSOL_MINT: (None, None)})
    r = _run(verify_receipt(
        kind=ReceiptKind.MSOL, chain="solana", owner=_OWNER, expected={},
    ))
    assert r.confirmed is False
    assert "no data" in r.detail.lower()


def test_msol_expected_amount_tolerance(monkeypatch):
    # balance roughly matches expected within 2% tolerance -> confirmed.
    _stub_token_balance(monkeypatch, by_mint={_MSOL_MINT: (1_000_000_000, 9)})
    r = _run(verify_receipt(
        kind=ReceiptKind.MSOL, chain="solana", owner=_OWNER,
        expected={"expected_amount": 1_005_000_000, "tolerance_bps": 200},
    ))
    assert r.confirmed is True


def test_msol_expected_amount_outside_tolerance(monkeypatch):
    # balance is half of expected -> drift 5000bps >> 200bps tol -> rejected.
    _stub_token_balance(monkeypatch, by_mint={_MSOL_MINT: (500_000_000, 9)})
    r = _run(verify_receipt(
        kind=ReceiptKind.MSOL, chain="solana", owner=_OWNER,
        expected={"expected_amount": 1_000_000_000, "tolerance_bps": 200},
    ))
    assert r.confirmed is False
    assert "drifted" in r.detail


# ─── JITOSOL ─────────────────────────────────────────────────────────────────

def test_jitosol_confirmed_when_balance_positive(monkeypatch):
    _stub_token_balance(monkeypatch, by_mint={_JITOSOL_MINT: (2_500_000_000, 9)})
    r = _run(verify_receipt(
        kind=ReceiptKind.JITOSOL, chain="solana", owner=_OWNER, expected={},
    ))
    assert r.confirmed is True
    assert r.raw["mint"] == _JITOSOL_MINT


def test_jitosol_rejected_when_balance_zero(monkeypatch):
    _stub_token_balance(monkeypatch, by_mint={_JITOSOL_MINT: (0, 9)})
    r = _run(verify_receipt(
        kind=ReceiptKind.JITOSOL, chain="solana", owner=_OWNER, expected={},
    ))
    assert r.confirmed is False


# ─── JLP ─────────────────────────────────────────────────────────────────────

def test_jlp_confirmed_when_balance_positive(monkeypatch):
    _stub_token_balance(monkeypatch, by_mint={_JLP_MINT: (123_456_789, 6)})
    r = _run(verify_receipt(
        kind=ReceiptKind.JLP, chain="solana", owner=_OWNER, expected={},
    ))
    assert r.confirmed is True
    assert r.raw["mint"] == _JLP_MINT


def test_jlp_rejected_when_balance_zero(monkeypatch):
    _stub_token_balance(monkeypatch, by_mint={_JLP_MINT: (0, 6)})
    r = _run(verify_receipt(
        kind=ReceiptKind.JLP, chain="solana", owner=_OWNER, expected={},
    ))
    assert r.confirmed is False


# ─── POSITION_PDA (Meteora DLMM — PDA only) ──────────────────────────────────

def test_position_pda_confirmed_when_account_exists(monkeypatch):
    _stub_account_exists(monkeypatch, exists=True,
                         account={"data": {"parsed": {"info": {"liquidity": "10000"}}}})
    r = _run(verify_receipt(
        kind=ReceiptKind.POSITION_PDA, chain="solana", owner=_OWNER,
        expected={"position_pda": "MeteoraDlmmPosPda11111111111111111111111111"},
    ))
    assert r.confirmed is True
    assert "exists" in r.detail


def test_position_pda_rejected_when_account_missing(monkeypatch):
    _stub_account_exists(monkeypatch, exists=False)
    r = _run(verify_receipt(
        kind=ReceiptKind.POSITION_PDA, chain="solana", owner=_OWNER,
        expected={"position_pda": "Missing11111111111111111111111111111111111"},
    ))
    assert r.confirmed is False
    assert "not found" in r.detail


def test_position_pda_requires_pda_address(monkeypatch):
    r = _run(verify_receipt(
        kind=ReceiptKind.POSITION_PDA, chain="solana", owner=_OWNER, expected={},
    ))
    assert r.confirmed is False
    assert "position_pda" in r.detail


# ─── POSITION_PDA_WITH_NFT (Orca Whirlpool / Raydium CLMM) ───────────────────

def test_position_pda_with_nft_confirmed_when_pda_exists_and_nft_held(monkeypatch):
    _stub_account_exists(monkeypatch, exists=True, account={"data": {}})
    nft_mint = "PosNftMint1111111111111111111111111111111111"
    _stub_token_balance(monkeypatch, by_mint={nft_mint: (1, 0)})
    r = _run(verify_receipt(
        kind=ReceiptKind.POSITION_PDA_WITH_NFT, chain="solana", owner=_OWNER,
        expected={
            "position_pda": "WhirlpoolPosPda11111111111111111111111111111",
            "position_mint": nft_mint,
        },
    ))
    assert r.confirmed is True, r.detail
    assert r.raw["nft_balance"] == 1


def test_position_pda_with_nft_rejected_when_nft_not_held(monkeypatch):
    _stub_account_exists(monkeypatch, exists=True, account={"data": {}})
    nft_mint = "PosNftMint1111111111111111111111111111111111"
    _stub_token_balance(monkeypatch, by_mint={nft_mint: (0, 0)})
    r = _run(verify_receipt(
        kind=ReceiptKind.POSITION_PDA_WITH_NFT, chain="solana", owner=_OWNER,
        expected={
            "position_pda": "WhirlpoolPosPda11111111111111111111111111111",
            "position_mint": nft_mint,
        },
    ))
    assert r.confirmed is False
    assert "does not hold" in r.detail


def test_position_pda_with_nft_requires_position_mint(monkeypatch):
    _stub_account_exists(monkeypatch, exists=True, account={"data": {}})
    r = _run(verify_receipt(
        kind=ReceiptKind.POSITION_PDA_WITH_NFT, chain="solana", owner=_OWNER,
        expected={"position_pda": "WhirlpoolPosPda11111111111111111111111111111"},
    ))
    assert r.confirmed is False
    assert "position_mint" in r.detail


# ─── OBLIGATION_STATE still delegates to sidecar ─────────────────────────────

def test_obligation_state_still_delegated_to_sidecar():
    # Synchronous kinds (OBLIGATION_STATE) still defer — borsh decode lives sidecar.
    r = _run(verify_receipt(
        kind=ReceiptKind.OBLIGATION_STATE, chain="solana", owner=_OWNER, expected={},
    ))
    assert r.confirmed is False
    assert "sidecar" in r.detail.lower()
