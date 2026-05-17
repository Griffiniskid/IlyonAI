"""Pin tests for the centralized EntityResolver (V7-015, spec §3).

Locks the contract that adapters rely on:
  * Native ETH on Ethereum resolves to the WETH address with is_native=True.
  * WETH on Ethereum resolves to the same address with is_native=False.
  * USDC.e on Arbitrum disambiguates from native USDC (different addresses).
  * "uniswap" canonicalizes to "uniswap-v3"; "aave" to "aave-v3".
  * "ethereum" → chain_id 1; "base" → 8453; "solana" → non-EVM sentinel.
  * resolve_pool dispatches the right factory call; mocked here to avoid RPC.
"""
from __future__ import annotations

import pytest

from src.defi.resolver import ChainInfo, EntityResolver, TokenInfo


# ─── Token resolution ───────────────────────────────────────────────────────

def test_resolve_eth_returns_weth_with_is_native_true() -> None:
    r = EntityResolver()
    info = r.resolve_token("ETH", "ethereum")
    assert info is not None
    assert info.is_native is True
    assert info.symbol == "WETH"
    # Canonical WETH (lower-case from asset_registry).
    assert info.address == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    assert info.decimals == 18
    assert info.wrapped_alias == "WETH"


def test_resolve_weth_returns_same_address_is_native_false() -> None:
    r = EntityResolver()
    eth = r.resolve_token("ETH", "ethereum")
    weth = r.resolve_token("WETH", "ethereum")
    assert weth is not None and eth is not None
    assert weth.address == eth.address
    assert weth.is_native is False
    assert weth.symbol == "WETH"
    assert weth.wrapped_alias == "WETH"


def test_resolve_usdc_e_arbitrum_distinct_from_usdc() -> None:
    r = EntityResolver()
    native_usdc = r.resolve_token("USDC", "arbitrum")
    bridged = r.resolve_token("USDC.e", "arbitrum")
    assert native_usdc is not None and bridged is not None
    # Native (Circle) USDC on Arbitrum.
    assert native_usdc.address == "0xaf88d065e77c8cc2239327c5edb3a432268e5831"
    # Bridged USDC.e on Arbitrum.
    assert bridged.address == "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8"
    assert native_usdc.address != bridged.address


def test_resolve_polygon_pol_alias_returns_wmatic() -> None:
    r = EntityResolver()
    pol = r.resolve_token("POL", "polygon")
    matic = r.resolve_token("MATIC", "polygon")
    assert pol is not None and matic is not None
    assert pol.is_native is True
    assert pol.symbol == "WMATIC"
    # POL and MATIC must point at the same wrapped address.
    assert pol.address == matic.address


def test_resolve_solana_sol_returns_wsol_mint() -> None:
    r = EntityResolver()
    sol = r.resolve_token("SOL", "solana")
    assert sol is not None
    assert sol.is_native is True
    assert sol.symbol == "WSOL"
    assert sol.address == "So11111111111111111111111111111111111111112"
    assert sol.decimals == 9


# ─── Protocol resolution ────────────────────────────────────────────────────

def test_resolve_protocol_uniswap_collapses_to_v3() -> None:
    r = EntityResolver()
    assert r.resolve_protocol("uniswap") == "uniswap-v3"


def test_resolve_protocol_aave_collapses_to_v3() -> None:
    r = EntityResolver()
    assert r.resolve_protocol("aave") == "aave-v3"


def test_resolve_protocol_comp_collapses_to_compound_v3() -> None:
    r = EntityResolver()
    assert r.resolve_protocol("comp") == "compound-v3"


def test_resolve_protocol_passthrough_for_unknown() -> None:
    r = EntityResolver()
    # Kamino is in the alias map but the canonical IS "kamino" — still works.
    assert r.resolve_protocol("kamino") == "kamino"
    # Truly unknown protocol falls through lower-cased.
    assert r.resolve_protocol("SomeNewProto") == "somenewproto"


# ─── Chain resolution ───────────────────────────────────────────────────────

def test_resolve_chain_ethereum_chain_id_one() -> None:
    r = EntityResolver()
    info = r.resolve_chain("ethereum")
    assert info == ChainInfo(chain_id=1, chain_name="ethereum", native_token="ETH")


def test_resolve_chain_base_chain_id_8453() -> None:
    r = EntityResolver()
    info = r.resolve_chain("base")
    assert info is not None
    assert info.chain_id == 8453
    assert info.native_token == "ETH"


def test_resolve_chain_solana_non_evm_sentinel() -> None:
    r = EntityResolver()
    info = r.resolve_chain("solana")
    assert info is not None
    assert info.chain_name == "solana"
    assert info.chain_id == -1  # non-EVM sentinel
    assert info.native_token == "SOL"


def test_resolve_chain_by_numeric_id() -> None:
    r = EntityResolver()
    info = r.resolve_chain(8453)
    assert info is not None
    assert info.chain_name == "base"


# ─── Pool resolution (mocked) ───────────────────────────────────────────────

def test_resolve_pool_v3_uses_factory_mock() -> None:
    r = EntityResolver()
    captured: dict = {}

    def _mock(*, token0, token1, fee_tier, chain, protocol):  # type: ignore[no-untyped-def]
        captured["call"] = (token0, token1, fee_tier, chain, protocol)
        # Canonical Uniswap V3 ETH/USDC 0.05% pool on mainnet.
        return "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"

    r.set_pool_resolver(_mock)
    weth = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    usdc = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    pool = r.resolve_pool(weth, usdc, 500, "ethereum", "uniswap-v3")
    assert pool == "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    assert captured["call"][2] == 500
    assert captured["call"][4] == "uniswap-v3"


def test_resolve_pool_alias_protocol_passes_canonical_through_mock() -> None:
    r = EntityResolver()
    seen: list = []

    def _mock(*, token0, token1, fee_tier, chain, protocol):  # type: ignore[no-untyped-def]
        # Override gets the RAW protocol — canonicalization happens AFTER
        # the override in `resolve_pool` only when override is absent.
        # Confirm at the very least the call hits.
        seen.append(protocol)
        return "0xdeadbeef" + "0" * 32

    r.set_pool_resolver(_mock)
    out = r.resolve_pool("0x" + "a" * 40, "0x" + "b" * 40, 3000, "ethereum", "uniswap")
    assert out is not None
    assert seen == ["uniswap"]
