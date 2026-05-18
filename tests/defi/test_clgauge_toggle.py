"""V7-048 — CLGauge toggle pin tests.

`stake_in_gauge` (default False) on Slipstream + Aerodrome CL adapters
appends a CLGauge.deposit(uint256 tokenId) step after the V3 mint so the
freshly-minted LP NFT is transferred into the gauge contract for emission
rewards (on top of standard fee accrual). When False, the NFT stays in the
caller's wallet and fees-only is the result. Uniswap / Pancake / Kodiak /
SwapX V3 families have no gauge — the toggle MUST be a no-op for them.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.uniswap_v3_nft import (
    _GAUGE_DEPOSIT_SEL,
    _GAUGED_PROTOCOLS,
    UniswapV3NFTAdapter,
    _encode_gauge_deposit,
    _resolve_gauge_address,
)


# ---------------------------------------------------------------------------
# Fake pool / network shims — keep the test offline.
# ---------------------------------------------------------------------------


@dataclass
class _FakePool:
    token0: str = "0x4200000000000000000000000000000000000006"  # WETH on Base
    token1: str = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"  # USDC on Base
    fee_bps: int = 500
    tick: int = -195000
    tick_spacing: int = 60
    sqrt_price_x96: int = 1583838586217683178694639878758  # rough WETH/USDC
    nfp_manager: str = "0x827922686190790b37229fd06084350e74485b72"  # Aerodrome NFP on Base
    liquidity: int = 1_000_000_000_000


async def _fake_resolve_v3_pool(*_a, **_kw):
    return _FakePool()


async def _fake_resolve_token(chain: str, sym: str):
    sym_u = (sym or "").strip()
    # Symbol map.
    by_sym = {
        "WETH": ("0x4200000000000000000000000000000000000006", 18),
        "USDC": ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
        "WBTC": ("0x0555E30da8f98308EdB960aa94C0Db47230d2B9c", 8),
        "WBNB": ("0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", 18),
        "WMATIC": ("0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", 18),
        "WAVAX": ("0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7", 18),
    }
    hit = by_sym.get(sym_u.upper())
    if hit:
        return hit
    # Address-keyed lookup (pool.token0/token1 are raw addresses).
    if isinstance(sym_u, str) and sym_u.lower().startswith("0x"):
        addr_l = sym_u.lower()
        if addr_l == "0x4200000000000000000000000000000000000006":
            return ("0x4200000000000000000000000000000000000006", 18)
        if addr_l == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913":
            return ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6)
    return None


class _FakeEnsoClient:
    async def build(self, **_kw):
        return {
            "unsigned_tx": {
                "to": "0x000000000022d473030f116ddee9f6b43ac78ba3",  # Permit2-ish
                "data": "0x" + "00" * 4,
                "value": "0x0",
            }
        }


def _patch_network(monkeypatch):
    import src.defi.execution.adapters.uniswap_v3_nft as mod

    monkeypatch.setattr(mod, "resolve_v3_pool", _fake_resolve_v3_pool, raising=True)
    monkeypatch.setattr(mod, "resolve_any_evm_token", _fake_resolve_token, raising=True)

    import src.routing.enso_client as enso_mod
    monkeypatch.setattr(enso_mod, "EnsoClient", _FakeEnsoClient, raising=True)

    # Block any DefiLlama oracle hop — the adapter catches exceptions and
    # falls back to stable=$1 hints, which is fine for this test's USDC pair.
    async def _no_oracle(*_a, **_kw):
        return None
    monkeypatch.setattr(mod, "fetch_price_usd", _no_oracle, raising=True)


def _build(adapter, *, protocol: str, monkeypatch, stake_in_gauge: bool):
    _patch_network(monkeypatch)
    req = YieldBuildRequest(
        chain="base",
        protocol=protocol,
        asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        slippage_bps=50,
        extra={
            "pool_symbol": "WETH-USDC",
            "fee_bps": 500,
            "stake_in_gauge": stake_in_gauge,
            # Hint USD prices so the deterministic ratio math works without
            # the oracle being reachable.
            "price_token0_usd": 2300.0,  # WETH
            "price_token1_usd": 1.0,     # USDC
        },
    )
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(adapter.build(req))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Helper-level pins — selector + gauge address must be exact.
# ---------------------------------------------------------------------------


def test_gauge_deposit_selector_pinned():
    # keccak256("deposit(uint256)")[:4] = 0xb6b55f25 — CLGauge ABI from
    # Aerodrome / Velodrome. Mis-pinning this selector silently sends to a
    # wrong function and the gauge will revert.
    data = _encode_gauge_deposit(12345)
    assert data.startswith(_GAUGE_DEPOSIT_SEL)
    assert _GAUGE_DEPOSIT_SEL == "0xb6b55f25"
    # tokenId 12345 = 0x3039 — must appear right-aligned in the 32-byte word.
    assert data.endswith("3039")


def test_gauged_protocol_set_contains_aerodrome_and_velodrome():
    # Both Slipstream-family (Aerodrome / Velodrome) protocols must be
    # gauge-eligible — Uniswap / Pancake V3 must not (no gauges).
    assert "aerodrome-slipstream" in _GAUGED_PROTOCOLS
    assert "aerodrome-cl" in _GAUGED_PROTOCOLS
    assert "velodrome-cl" in _GAUGED_PROTOCOLS
    assert "velodrome-slipstream" in _GAUGED_PROTOCOLS
    assert "uniswap-v3" not in _GAUGED_PROTOCOLS
    assert "pancakeswap-v3" not in _GAUGED_PROTOCOLS


def test_resolve_gauge_address_returns_per_protocol_placeholder():
    aero = _resolve_gauge_address("aerodrome-slipstream", None)
    velo = _resolve_gauge_address("velodrome-cl", None)
    assert aero.startswith("0x") and len(aero) == 42
    assert velo.startswith("0x") and len(velo) == 42
    assert aero != velo  # per-protocol distinct placeholders


# ---------------------------------------------------------------------------
# End-to-end build pins — toggle must add exactly one extra step.
# ---------------------------------------------------------------------------


def test_slipstream_default_no_gauge_stake(monkeypatch):
    """Default (stake_in_gauge omitted) keeps LP NFT in wallet — no stake step."""
    adapter = UniswapV3NFTAdapter()
    steps = _build(adapter, protocol="aerodrome-slipstream", monkeypatch=monkeypatch, stake_in_gauge=False)
    actions = [s.action for s in steps]
    assert "stake" not in actions, f"Default must NOT stake; got actions {actions}"
    assert "deposit_lp" in actions


def test_slipstream_stake_in_gauge_appends_stake_step(monkeypatch):
    """stake_in_gauge=True on Slipstream MUST append a `stake` step with the
    CLGauge.deposit(uint256) selector."""
    adapter = UniswapV3NFTAdapter()
    on = _build(adapter, protocol="aerodrome-slipstream", monkeypatch=monkeypatch, stake_in_gauge=True)
    off = _build(adapter, protocol="aerodrome-slipstream", monkeypatch=monkeypatch, stake_in_gauge=False)
    assert len(on) == len(off) + 1, f"Toggle must add exactly 1 step. on={len(on)} off={len(off)}"
    last = on[-1]
    assert last.action == "stake"
    assert last.transaction.data.startswith(_GAUGE_DEPOSIT_SEL)
    # Mint step still present immediately before the stake.
    assert on[-2].action == "deposit_lp"


def test_aerodrome_cl_stake_in_gauge_appends_stake_step(monkeypatch):
    """Aerodrome CL alias must follow the same pattern as Slipstream."""
    adapter = UniswapV3NFTAdapter()
    on = _build(adapter, protocol="aerodrome-cl", monkeypatch=monkeypatch, stake_in_gauge=True)
    off = _build(adapter, protocol="aerodrome-cl", monkeypatch=monkeypatch, stake_in_gauge=False)
    assert len(on) == len(off) + 1
    assert on[-1].action == "stake"
    assert on[-1].transaction.data.startswith(_GAUGE_DEPOSIT_SEL)


def test_uniswap_v3_stake_in_gauge_is_noop(monkeypatch):
    """Uniswap V3 has no gauge — toggle MUST be a no-op even when True."""
    adapter = UniswapV3NFTAdapter()
    on = _build(adapter, protocol="uniswap-v3", monkeypatch=monkeypatch, stake_in_gauge=True)
    actions = [s.action for s in on]
    assert "stake" not in actions, f"Uniswap V3 must not get a gauge step; got {actions}"
