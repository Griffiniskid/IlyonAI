"""Tests for src/defi/verification/receipt_reader.py."""
from __future__ import annotations

import asyncio
import pytest

from src.defi.verification.receipt_reader import (
    _pad32,
    _BALANCE_OF_SEL,
    _NFP_POSITIONS_SEL,
    verify_receipt,
    ReadResult,
)
from src.defi.verification.receipt_table import ReceiptKind


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_pad32_lowercases_and_pads():
    assert _pad32("0xABCD") == "0" * 60 + "abcd"
    assert _pad32("0x" + "f" * 40) == "0" * 24 + "f" * 40


def test_balance_selector():
    assert _BALANCE_OF_SEL == "0x70a08231"


def test_nfp_positions_selector():
    assert _NFP_POSITIONS_SEL == "0x99fbab88"


def test_verify_receipt_solana_kind_returns_delegated(monkeypatch):
    # MSOL is chain_family=solana per receipt_table — verify_receipt must
    # short-circuit with the delegation message instead of attempting an RPC.
    r = _run(verify_receipt(
        kind=ReceiptKind.MSOL, chain="solana", owner="0xabc", expected={},
    ))
    assert isinstance(r, ReadResult)
    assert r.confirmed is False
    assert "Solana" in r.detail and "sidecar" in r.detail.lower()


def test_verify_receipt_unknown_kind_returns_no_spec():
    r = _run(verify_receipt(
        kind="UNKNOWN_KIND_XYZ", chain="ethereum", owner="0xabc", expected={},
    ))
    assert r.confirmed is False
    assert "No verifier spec" in r.detail


def test_verify_receipt_balance_kind_requires_token_in_expected(monkeypatch):
    # Patch the RPC layer so the test stays offline.
    async def _fake_call(*a, **kw):
        return None
    import src.defi.verification.receipt_reader as mod
    monkeypatch.setattr(mod, "_eth_call_with_fallback", _fake_call)
    r = _run(verify_receipt(
        kind=ReceiptKind.ATOKEN, chain="ethereum", owner="0xabc", expected={},
    ))
    assert r.confirmed is False
    assert "token / vault / lp_token" in r.detail


def test_verify_receipt_balance_kind_reads_rpc(monkeypatch):
    # Stub the RPC to return a non-zero balance (0x...64 == 100).
    async def _fake_call(chain, to, data):
        return "0x" + "0" * 62 + "64"
    import src.defi.verification.receipt_reader as mod
    monkeypatch.setattr(mod, "_eth_call_with_fallback", _fake_call)
    r = _run(verify_receipt(
        kind=ReceiptKind.ERC4626_SHARE, chain="ethereum",
        owner="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        expected={"vault": "0xbbbb", "min_expected": 50},
    ))
    assert r.confirmed is True
    assert "100" in r.detail
    assert r.raw["balance"] == 100


def test_verify_receipt_v4_nft_requires_pool_manager(monkeypatch):
    async def _fake_call(*a, **kw):
        return None
    import src.defi.verification.receipt_reader as mod
    monkeypatch.setattr(mod, "_eth_call_with_fallback", _fake_call)
    r = _run(verify_receipt(
        kind=ReceiptKind.V4_NFT, chain="ethereum", owner="0xabc", expected={},
    ))
    assert r.confirmed is False
    assert "pool_manager" in r.detail


def test_verify_receipt_v4_nft_decodes_liquidity(monkeypatch):
    # Mock PoolManager.getPositionInfo to return non-zero liquidity (0x...64 = 100).
    async def _fake_call(chain, to, data):
        # 3 × 32-byte words: liquidity=100, feeGrowth0=0, feeGrowth1=0
        return "0x" + "0" * 62 + "64" + "0" * 64 + "0" * 64
    import src.defi.verification.receipt_reader as mod
    monkeypatch.setattr(mod, "_eth_call_with_fallback", _fake_call)
    r = _run(verify_receipt(
        kind=ReceiptKind.V4_NFT, chain="ethereum",
        owner="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        expected={
            "pool_manager": "0x000000000004444c5dc75cB358380D2e3dE08A90",
            "pool_id": "0x" + "ab" * 32,
            "position_id": "0x" + "cd" * 32,
        },
    ))
    assert r.confirmed is True
    assert r.raw["liquidity"] == 100


def test_verify_receipt_balance_below_min(monkeypatch):
    async def _fake_call(chain, to, data):
        return "0x" + "0" * 62 + "0a"  # 10
    import src.defi.verification.receipt_reader as mod
    monkeypatch.setattr(mod, "_eth_call_with_fallback", _fake_call)
    r = _run(verify_receipt(
        kind=ReceiptKind.CTOKEN, chain="ethereum",
        owner="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        expected={"token": "0xbbbb", "min_expected": 100},
    ))
    assert r.confirmed is False
    assert "10" in r.detail


def test_verify_receipt_v3_nft_with_liquidity(monkeypatch):
    """V3_NFT confirms when NFP.positions(tokenId).liquidity > 0."""
    async def _fake_call(chain, to, data):
        # 12-word return: nonce, operator, token0, token1, fee, tickLower,
        # tickUpper, liquidity=42, ...
        # Fill 12 × 32 = 384 bytes; only liquidity word matters here.
        body = "00" * 32 * 7  # words 0..6
        body += "00" * 31 + "2a"  # word 7 liquidity = 42
        body += "00" * 32 * 4    # words 8..11
        return "0x" + body
    import src.defi.verification.receipt_reader as mod
    monkeypatch.setattr(mod, "_eth_call_with_fallback", _fake_call)
    r = _run(verify_receipt(
        kind=ReceiptKind.V3_NFT, chain="ethereum",
        owner="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        expected={"nfpm": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88", "token_id": 12345},
    ))
    assert r.confirmed is True
    assert r.raw["liquidity"] == 42


def test_verify_receipt_v3_nft_requires_nfpm(monkeypatch):
    r = _run(verify_receipt(
        kind=ReceiptKind.V3_NFT, chain="ethereum", owner="0xabc", expected={},
    ))
    assert r.confirmed is False
    assert "nfpm" in r.detail
