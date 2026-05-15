"""ReceiptWatcher.verify_step_receipt integration with verify_receipt()."""
from __future__ import annotations

import asyncio

import pytest

from src.agent.receipt_watcher import (
    ReceiptWatcher,
    resolve_receipt_kind,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _dummy_rpc(method, params):
    async def _r():
        return None
    return _r()


def test_resolve_kind_for_aave_supply():
    assert resolve_receipt_kind("aave-v3", "supply") == "ATOKEN"
    assert resolve_receipt_kind("AAVE-V3", "SUPPLY") == "ATOKEN"


def test_resolve_kind_for_uniswap_v3_lp():
    assert resolve_receipt_kind("uniswap-v3", "deposit_lp") == "V3_NFT"


def test_resolve_kind_for_uniswap_v4_lp():
    assert resolve_receipt_kind("uniswap-v4", "add_liquidity") == "V4_NFT"


def test_resolve_kind_for_lido_stake():
    assert resolve_receipt_kind("lido", "stake") == "LST_ERC20"


def test_resolve_kind_for_renzo_stake():
    assert resolve_receipt_kind("renzo", "stake") == "LRT_ERC20"


def test_resolve_kind_for_compound_v3():
    assert resolve_receipt_kind("compound-v3", "supply") == "CTOKEN"


def test_resolve_kind_for_marinade():
    assert resolve_receipt_kind("marinade", "stake") == "MSOL"


def test_resolve_kind_for_unknown_returns_none():
    assert resolve_receipt_kind("imaginary-protocol", "deposit") is None
    assert resolve_receipt_kind("aave-v3", "imaginary-action") is None


def test_resolve_kind_handles_none_args():
    assert resolve_receipt_kind(None, "supply") is None
    assert resolve_receipt_kind("aave-v3", None) is None


def test_verify_step_receipt_returns_skip_when_no_kind():
    w = ReceiptWatcher(rpc_call=_dummy_rpc)
    r = _run(w.verify_step_receipt(
        protocol="imaginary", action="action", chain="ethereum", owner="0xabc",
    ))
    assert r["confirmed"] is False
    assert "No receipt verifier spec" in r["detail"]


def test_verify_step_receipt_returns_dict_for_msol(monkeypatch):
    """Marinade stake maps to MSOL ReceiptKind — verify_receipt returns
    the chain_family=solana short-circuit message."""
    w = ReceiptWatcher(rpc_call=_dummy_rpc)
    r = _run(w.verify_step_receipt(
        protocol="marinade", action="stake", chain="solana", owner="abcabc",
    ))
    assert isinstance(r, dict)
    assert "confirmed" in r and "detail" in r
    # Solana side returns confirmed=False with sidecar delegation note.
    assert r["confirmed"] is False
    assert "Solana" in r["detail"]


def test_verify_step_receipt_balance_kind_calls_reader(monkeypatch):
    """ATOKEN kind triggers a balanceOf RPC read through verify_receipt."""
    import src.defi.verification.receipt_reader as mod

    # Stub the RPC layer so the test stays offline.
    async def _fake_call(chain, to, data):
        # Return 0x..64 = 100 raw, well above min_expected.
        return "0x" + "0" * 62 + "64"

    monkeypatch.setattr(mod, "_eth_call_with_fallback", _fake_call)
    w = ReceiptWatcher(rpc_call=_dummy_rpc)
    r = _run(w.verify_step_receipt(
        protocol="aave-v3", action="supply", chain="ethereum",
        owner="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        expected={"token": "0xbbbb", "min_expected": 50},
    ))
    assert r["confirmed"] is True
    assert r["raw"].get("balance") == 100
    assert r["kind"] == "ATOKEN"
