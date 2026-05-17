"""Pin tests for Berachain Kodiak V3 + Sonic SwapX (Algebra Integral) V3 registry.

Asserts that V3_FACTORIES returns the exact on-chain-verified factory,
NonfungiblePositionManager, SwapRouter, and family tag for each entry, and
that the adapter's protocol set claims support for both.
"""
from __future__ import annotations

from src.data.v3_pool_resolver import V3_FACTORIES
from src.defi.execution.adapters.uniswap_v3_nft import (
    _CHAIN_IDS,
    _SUPPORTED_PROTOCOLS,
    UniswapV3NFTAdapter,
)


# --- Kodiak (Berachain, chain 80094) — Uniswap V3 family --------------------

def test_kodiak_factory_address():
    cfg = V3_FACTORIES[("berachain", "kodiak-v3")]
    assert cfg["factory"] == "0xD84CBf0B02636E7f53dB9E5e45A616E05d710990"


def test_kodiak_nfp_manager_address():
    cfg = V3_FACTORIES[("berachain", "kodiak-v3")]
    assert cfg["nfp_manager"] == "0xFE5E8C83FFE4d9627A75EaA7Fee864768dB989bD"


def test_kodiak_swap_router_address():
    cfg = V3_FACTORIES[("berachain", "kodiak-v3")]
    assert cfg["swap_router"] == "0xEd158C4b336A6FCb5B193A5570e3a571f6cbe690"


def test_kodiak_family_uniswap_v3():
    cfg = V3_FACTORIES[("berachain", "kodiak-v3")]
    assert cfg["family"] == "uniswap_v3"


def test_berachain_chain_id_80094():
    assert _CHAIN_IDS["berachain"] == 80094


def test_kodiak_in_supported_protocols():
    assert "kodiak-v3" in _SUPPORTED_PROTOCOLS


# --- SwapX (Sonic, chain 146) — Algebra Integral family ---------------------

def test_swapx_factory_address():
    cfg = V3_FACTORIES[("sonic", "swapx-v4")]
    assert cfg["factory"] == "0x8121a3F8c4176E9765deEa0B95FA2BDfD3016794"


def test_swapx_nfp_manager_address():
    cfg = V3_FACTORIES[("sonic", "swapx-v4")]
    assert cfg["nfp_manager"] == "0xd82Fe82244ad01AaD671576202F9b46b76fAdFE2"


def test_swapx_swap_router_address():
    cfg = V3_FACTORIES[("sonic", "swapx-v4")]
    assert cfg["swap_router"] == "0xE6E9F79e551Dd3FAeF8aBe035896fc65A9eEB26c"


def test_swapx_family_algebra_integral():
    """SwapX is Algebra Integral V4 — DIFFERENT ABI from Uniswap V3 (no fixed
    fee tuple in mint; factory.getPool drops the uint24 fee param). Must be
    flagged separately so downstream mint encoders branch on it."""
    cfg = V3_FACTORIES[("sonic", "swapx-v4")]
    assert cfg["family"] == "algebra_integral"


def test_sonic_chain_id_146():
    assert _CHAIN_IDS["sonic"] == 146


def test_swapx_in_supported_protocols():
    assert "swapx-v4" in _SUPPORTED_PROTOCOLS


# --- Adapter capability surface --------------------------------------------

def test_adapter_supports_kodiak_on_berachain():
    a = UniswapV3NFTAdapter()
    res = a.supports(chain="berachain", protocol="kodiak-v3", action="deposit_lp")
    # supports() returns False without ENSO_API_KEY but still must NOT reject
    # the chain or protocol. Walk the reason string to assert the rejection is
    # only the api-key gate, never an unsupported-chain/protocol gate.
    if not res.supported:
        assert "ENSO_API_KEY" in (res.reason or "")
    else:
        assert res.adapter_id == "uniswap-v3-nft"


def test_adapter_supports_swapx_on_sonic():
    a = UniswapV3NFTAdapter()
    res = a.supports(chain="sonic", protocol="swapx-v4", action="deposit_lp")
    if not res.supported:
        assert "ENSO_API_KEY" in (res.reason or "")
    else:
        assert res.adapter_id == "uniswap-v3-nft"
