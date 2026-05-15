"""Tests for src/defi/execution/lst_registry.py."""
from __future__ import annotations

from src.defi.execution.lst_registry import (
    LstEntry,
    DirectMintPath,
    SecondaryMarketPath,
    lookup_lst,
    all_entries,
    chains_for_symbol,
)


def test_lido_steth_present_with_direct_mint():
    e = lookup_lst("ethereum", "stETH")
    assert isinstance(e, LstEntry)
    assert e.protocol == "lido"
    assert e.receipt_token == "stETH"
    assert e.direct_mint is not None
    assert e.direct_mint.native_eth is True
    assert e.direct_mint.contract.startswith("0xae7ab96")


def test_lido_secondary_market_curve():
    e = lookup_lst("ethereum", "stETH")
    assert e.secondary_market is not None
    assert e.secondary_market.venue == "curve"
    assert e.secondary_market.paired_with == "ETH"


def test_rocket_pool_reth():
    e = lookup_lst("ethereum", "rETH")
    assert e.protocol == "rocket-pool"
    assert e.direct_mint and e.direct_mint.native_eth
    assert e.secondary_market and e.secondary_market.venue == "balancer"


def test_lrt_set_present():
    for symbol in ("ezETH", "rsETH", "rswETH", "pufETH"):
        e = lookup_lst("ethereum", symbol)
        assert e is not None, f"{symbol} missing"
        assert e.direct_mint is not None


def test_kelp_rseth_erc20_path():
    e = lookup_lst("ethereum", "rsETH")
    assert e.direct_mint.native_eth is False
    # depositAsset(asset, amount) selector
    assert e.direct_mint.selector == "0x47e7ef24"


def test_all_entries_returns_list():
    entries = all_entries()
    assert len(entries) >= 8
    symbols = {e.symbol for e in entries}
    assert "stETH" in symbols
    assert "ezETH" in symbols


def test_chains_for_symbol():
    chains = chains_for_symbol("stETH")
    assert "ethereum" in chains


def test_unknown_lookup_returns_none():
    assert lookup_lst("ethereum", "GARBAGE_TOKEN") is None
    assert lookup_lst("ethereum", "stETH") is not None


def test_direct_mint_selectors_are_4bytes():
    for e in all_entries():
        if e.direct_mint is None:
            continue
        sel = e.direct_mint.selector
        assert sel.startswith("0x") and len(sel) == 10
