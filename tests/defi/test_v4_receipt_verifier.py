"""Pin tests for Uniswap V4 PoolManager.getPositionInfo receipt verifier — spec §6g.

Covers the 3-arg variant `getPositionInfo(bytes32 poolId, address owner, bytes32 salt)`
introduced by `src/defi/execution/adapters/uniswap_v4.py::_verify_v4_position`.

Selector pin: keccak256("getPositionInfo(bytes32,address,bytes32)")[:4] == 0xfba8dbd4
(verified offline 2026-05-19 via pycryptodome).
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

import src.defi.execution.adapters.uniswap_v4 as v4_mod
from src.defi.execution.adapters.base import YieldVerifyRequest
from src.defi.execution.adapters.uniswap_v4 import (
    UniswapV4NativeAdapter,
    _V4_GETPOSINFO3_SEL,
    _V4_POOL_MANAGER,
    _verify_v4_position,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _word(value: int) -> str:
    """64-hex-char big-endian word (32 bytes)."""
    if value < 0:
        value = value & ((1 << 256) - 1)
    return format(value, "064x")


# ---------------------------------------------------------------------------
# Selector pin — must match keccak256(sig)[:4]
# ---------------------------------------------------------------------------
def test_v4_getpositioninfo_selector_pin():
    """Selector pinned to 0xfba8dbd4.

    Independently re-derive via eth_utils.keccak (already a project dep) and
    confirm equality with the constant the adapter uses. This guards against
    accidental rebinding of the selector to the legacy 2-arg variant.
    """
    try:
        from eth_utils import keccak as _keccak
    except ImportError:
        pytest.skip("eth_utils not installed")
    sig = b"getPositionInfo(bytes32,address,bytes32)"
    expected = "0x" + _keccak(sig).hex()[:8]
    assert _V4_GETPOSINFO3_SEL == expected == "0xfba8dbd4"


def test_v4_getpositioninfo_selector_not_confused_with_2arg():
    """Ensure we are NOT using the 2-arg variant 0x97fd7b42 used by the
    sidecar receipt_reader path (different semantics — that one takes
    poolId+positionId, this one takes poolId+owner+salt)."""
    assert _V4_GETPOSINFO3_SEL != "0x97fd7b42"


# ---------------------------------------------------------------------------
# _verify_v4_position direct tests (RPC mocked)
# ---------------------------------------------------------------------------
POOL_ID = "0x" + "ab" * 32
OWNER = "0x" + "11" * 20
SALT = "0x" + "00" * 32
PM = _V4_POOL_MANAGER["ethereum"]


def test_verify_v4_position_zero_liquidity_returns_false(monkeypatch):
    async def _fake_call(chain, to, data):
        assert data.startswith(_V4_GETPOSINFO3_SEL)
        # Zero liquidity, zero fee growth.
        return "0x" + _word(0) + _word(0) + _word(0)
    monkeypatch.setattr(v4_mod, "_eth_call_with_fallback", _fake_call)
    confirmed, payload = _run(_verify_v4_position(
        pool_id=POOL_ID, owner=OWNER, salt=SALT,
        chain="ethereum", pool_manager=PM,
    ))
    assert confirmed is False
    assert payload["liquidity"] == 0


def test_verify_v4_position_nonzero_liquidity_returns_true_with_payload(monkeypatch):
    async def _fake_call(chain, to, data):
        # liquidity=12345, fee_growth_0=2**100, fee_growth_1=2**101
        return "0x" + _word(12345) + _word(2**100) + _word(2**101)
    monkeypatch.setattr(v4_mod, "_eth_call_with_fallback", _fake_call)
    confirmed, payload = _run(_verify_v4_position(
        pool_id=POOL_ID, owner=OWNER, salt=SALT,
        chain="ethereum", pool_manager=PM,
    ))
    assert confirmed is True
    assert payload["liquidity"] == 12345
    assert payload["fee_growth_0"] == 2**100
    assert payload["fee_growth_1"] == 2**101
    assert payload["pool_id"] == POOL_ID
    assert payload["owner"] == OWNER
    assert payload["salt"] == SALT


def test_verify_v4_position_empty_rpc_returns_false(monkeypatch):
    async def _fake_call(chain, to, data):
        return "0x"
    monkeypatch.setattr(v4_mod, "_eth_call_with_fallback", _fake_call)
    confirmed, payload = _run(_verify_v4_position(
        pool_id=POOL_ID, owner=OWNER, salt=SALT,
        chain="ethereum", pool_manager=PM,
    ))
    assert confirmed is False
    assert payload["reason"] == "rpc_empty"


def test_verify_v4_position_calldata_layout(monkeypatch):
    """The 196-byte calldata is `selector || poolId || owner_padded || salt`."""
    captured: dict = {}

    async def _fake_call(chain, to, data):
        captured["data"] = data
        captured["to"] = to
        captured["chain"] = chain
        return "0x" + _word(7) + _word(0) + _word(0)

    monkeypatch.setattr(v4_mod, "_eth_call_with_fallback", _fake_call)
    _run(_verify_v4_position(
        pool_id=POOL_ID, owner=OWNER, salt=SALT,
        chain="ethereum", pool_manager=PM,
    ))
    d = captured["data"]
    assert d.startswith(_V4_GETPOSINFO3_SEL)
    # 4 bytes selector + 3 × 32 bytes args = 8 + 192 = 200 hex chars + "0x"
    assert len(d) == 2 + 8 + 192
    # poolId word
    assert d[10:74] == POOL_ID.removeprefix("0x")
    # owner word — left-padded to 32 bytes
    assert d[74:138] == "00" * 12 + OWNER.removeprefix("0x")
    # salt word
    assert d[138:202] == SALT.removeprefix("0x")
    assert captured["to"] == PM
    assert captured["chain"] == "ethereum"


# ---------------------------------------------------------------------------
# UniswapV4NativeAdapter.verify() end-to-end (RPC mocked)
# ---------------------------------------------------------------------------
def test_adapter_verify_liquidity_zero_returns_false(monkeypatch):
    async def _fake_call(chain, to, data):
        return "0x" + _word(0) + _word(0) + _word(0)
    monkeypatch.setattr(v4_mod, "_eth_call_with_fallback", _fake_call)
    adapter = UniswapV4NativeAdapter()
    req = YieldVerifyRequest(
        chain="ethereum",
        user_address=OWNER,
        expected_position={"pool_id": POOL_ID, "salt": SALT},
    )
    r = _run(adapter.verify(req))
    assert r.confirmed is False
    assert "liquidity=0" in r.detail


def test_adapter_verify_liquidity_nonzero_returns_true_with_echo(monkeypatch):
    async def _fake_call(chain, to, data):
        return "0x" + _word(12345) + _word(99) + _word(101)
    monkeypatch.setattr(v4_mod, "_eth_call_with_fallback", _fake_call)
    adapter = UniswapV4NativeAdapter()
    req = YieldVerifyRequest(
        chain="ethereum",
        user_address=OWNER,
        expected_position={"pool_id": POOL_ID, "salt": SALT},
    )
    r = _run(adapter.verify(req))
    assert r.confirmed is True
    assert r.receipt["liquidity"] == 12345
    assert r.receipt["fee_growth_0"] == 99
    assert r.receipt["fee_growth_1"] == 101
    # Payload echoes the input keying triple
    assert r.receipt["pool_id"] == POOL_ID
    assert r.receipt["owner"] == OWNER
    assert r.receipt["salt"] == SALT


def test_adapter_verify_missing_pool_manager_returns_stub(monkeypatch):
    """Unknown chain → STUB_NO_POOL_MANAGER + confirmed=False, no RPC call issued."""
    called = {"n": 0}

    async def _fake_call(*a, **kw):
        called["n"] += 1
        return "0x" + _word(999) + _word(0) + _word(0)

    monkeypatch.setattr(v4_mod, "_eth_call_with_fallback", _fake_call)
    adapter = UniswapV4NativeAdapter()
    req = YieldVerifyRequest(
        chain="zksync",  # not in _V4_POOL_MANAGER
        user_address=OWNER,
        expected_position={"pool_id": POOL_ID, "salt": SALT},
    )
    r = _run(adapter.verify(req))
    assert r.confirmed is False
    assert "STUB_NO_POOL_MANAGER" in r.detail
    assert r.receipt["reason"] == "STUB_NO_POOL_MANAGER"
    assert r.receipt["chain"] == "zksync"
    assert called["n"] == 0  # never reached RPC


def test_adapter_verify_missing_pool_id_refuses(monkeypatch):
    adapter = UniswapV4NativeAdapter()
    req = YieldVerifyRequest(
        chain="ethereum",
        user_address=OWNER,
        expected_position={"salt": SALT},  # missing pool_id
    )
    r = _run(adapter.verify(req))
    assert r.confirmed is False
    assert "pool_id" in r.detail


def test_adapter_verify_missing_owner_refuses():
    adapter = UniswapV4NativeAdapter()
    req = YieldVerifyRequest(
        chain="ethereum",
        user_address="",  # missing
        expected_position={"pool_id": POOL_ID, "salt": SALT},
    )
    r = _run(adapter.verify(req))
    assert r.confirmed is False
    assert "owner" in r.detail


def test_adapter_verify_defaults_salt_to_zero(monkeypatch):
    """If no salt is supplied, the canonical zero salt (V4 default) is used."""
    captured = {}

    async def _fake_call(chain, to, data):
        captured["data"] = data
        return "0x" + _word(1) + _word(0) + _word(0)

    monkeypatch.setattr(v4_mod, "_eth_call_with_fallback", _fake_call)
    adapter = UniswapV4NativeAdapter()
    req = YieldVerifyRequest(
        chain="ethereum",
        user_address=OWNER,
        expected_position={"pool_id": POOL_ID},  # no salt
    )
    r = _run(adapter.verify(req))
    assert r.confirmed is True
    # last 32-byte word should be all zeros
    assert captured["data"][-64:] == "0" * 64
