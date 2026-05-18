"""V7-055 — pin test for per-chain LST receipt-address registry.

Tests for `lst_for_chain(protocol, chain_id)` accessor and the underlying
`LST_REGISTRY` shape introduced in V7-055 / src/defi/execution/lst_registry.py.

Note: tests/data/ is gitignored at the repo level (by the bare `data/`
.gitignore rule). The test was force-added with `git add -f`.
"""
from __future__ import annotations

import pytest

from src.defi.execution.lst_registry import (
    LST_REGISTRY,
    all_protocols,
    lst_for_chain,
    supported_chains_for_protocol,
)


# ── canonical per-chain wstETH addresses (verified against block explorers) ──
WSTETH_ETH = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"
WSTETH_ARB = "0x5979D7b546E38E414F7E9822514be443A4800529"
WSTETH_OPT = "0x1F32b1c2345538c0c6f582fCB022739c4A194Ebb"
WSTETH_BASE = "0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452"
WSTETH_LINEA = "0xB5beDd42000b71FddE22D3eE8a79Bd49A568fC8F"
CBETH_BASE = "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22"


# ─────────────────────────────────────────────────────────────────────────────
# Required pin tests (per spec)
# ─────────────────────────────────────────────────────────────────────────────


def test_lido_ethereum_returns_wsteth_mainnet():
    """lst_for_chain('lido', 1) returns wstETH on ethereum."""
    entry = lst_for_chain("lido", 1)
    assert entry is not None, "lido on chain 1 must be registered"
    assert entry["receipt_addr"].lower() == WSTETH_ETH.lower()
    assert entry["symbol"] == "wstETH"
    assert entry["decimals"] == 18


def test_lido_arbitrum_returns_bridged_wsteth_different_addr():
    """lst_for_chain('lido', 42161) returns wstETH bridged on Arb (different addr)."""
    entry = lst_for_chain("lido", 42161)
    assert entry is not None
    assert entry["receipt_addr"].lower() == WSTETH_ARB.lower()
    assert entry["symbol"] == "wstETH"
    # critical: must differ from mainnet receipt addr
    eth_entry = lst_for_chain("lido", 1)
    assert entry["receipt_addr"].lower() != eth_entry["receipt_addr"].lower()


def test_lido_base_returns_base_wsteth_addr():
    """lst_for_chain('lido', 8453) returns Base addr."""
    entry = lst_for_chain("lido", 8453)
    assert entry is not None
    assert entry["receipt_addr"].lower() == WSTETH_BASE.lower()


def test_coinbase_base_returns_cbeth_on_base():
    """lst_for_chain('coinbase', 8453) returns cbETH on Base."""
    entry = lst_for_chain("coinbase", 8453)
    assert entry is not None
    assert entry["receipt_addr"].lower() == CBETH_BASE.lower()
    assert entry["symbol"] == "cbETH"


def test_unknown_protocol_returns_none():
    """lst_for_chain('unknown', 1) returns None."""
    assert lst_for_chain("unknown", 1) is None
    assert lst_for_chain("not_a_protocol", 8453) is None


# ─────────────────────────────────────────────────────────────────────────────
# Bonus coverage — chain/protocol surface
# ─────────────────────────────────────────────────────────────────────────────


def test_lido_optimism_and_linea_addresses_pinned():
    """Op + Linea wstETH addrs are pinned to the spec-provided values."""
    op = lst_for_chain("lido", 10)
    li = lst_for_chain("lido", 59144)
    assert op is not None and li is not None
    assert op["receipt_addr"].lower() == WSTETH_OPT.lower()
    assert li["receipt_addr"].lower() == WSTETH_LINEA.lower()


def test_lst_for_chain_returns_none_for_unsupported_chain():
    """Known protocol but un-registered chain returns None (no crash)."""
    # Mantle is mainnet-only in registry
    assert lst_for_chain("mantle", 8453) is None
    assert lst_for_chain("mantle", 42161) is None
    # but mainnet still works
    assert lst_for_chain("mantle", 1) is not None


def test_protocol_lookup_case_insensitive():
    """Protocol key should normalize to lowercase."""
    assert lst_for_chain("LIDO", 1) is not None
    assert lst_for_chain("Coinbase", 8453) is not None


def test_returned_entry_is_copy_not_reference():
    """Mutating the returned dict must not pollute the registry."""
    entry = lst_for_chain("lido", 1)
    entry["receipt_addr"] = "0xDEADBEEF"
    fresh = lst_for_chain("lido", 1)
    assert fresh["receipt_addr"] != "0xDEADBEEF"


def test_all_lst_chains_have_required_fields():
    """Every (protocol, chain_id) entry has receipt_addr, decimals, symbol."""
    for proto, by_chain in LST_REGISTRY.items():
        assert isinstance(by_chain, dict) and by_chain, f"{proto} has empty chain map"
        for chain_id, entry in by_chain.items():
            assert isinstance(chain_id, int), f"{proto}: non-int chain_id {chain_id}"
            for field in ("receipt_addr", "decimals", "symbol", "minter"):
                assert field in entry, f"{proto}/{chain_id} missing {field}"
            assert entry["receipt_addr"].startswith("0x"), (
                f"{proto}/{chain_id} receipt_addr not hex"
            )
            assert len(entry["receipt_addr"]) == 42, (
                f"{proto}/{chain_id} receipt_addr wrong length"
            )
            assert isinstance(entry["decimals"], int) and entry["decimals"] > 0


def test_required_chains_covered_for_lido():
    """Spec requires Lido on chains 1, 8453, 42161, 10, 59144."""
    chains = set(supported_chains_for_protocol("lido"))
    assert {1, 10, 8453, 42161, 59144}.issubset(chains)


def test_required_chains_covered_for_coinbase():
    """cbETH must be on Base per spec."""
    chains = set(supported_chains_for_protocol("coinbase"))
    assert 8453 in chains
    assert 1 in chains


def test_all_protocols_listed():
    """all_protocols() returns sorted lowercase keys, includes known protocols."""
    protos = all_protocols()
    assert protos == sorted(protos)
    for required in ("lido", "coinbase", "rocket-pool", "ether.fi", "renzo", "kelp"):
        assert required in protos


def test_chain_id_string_coercion():
    """chain_id passed as int subclass / bool-like should still work via int()."""
    # bool is subclass of int — chain_id=True coerces to 1
    assert lst_for_chain("lido", True) is not None  # noqa: FBT003


@pytest.mark.parametrize(
    "protocol,chain_id,expected_symbol",
    [
        ("lido", 1, "wstETH"),
        ("lido", 42161, "wstETH"),
        ("lido", 8453, "wstETH"),
        ("coinbase", 8453, "cbETH"),
        ("rocket-pool", 1, "rETH"),
        ("ether.fi", 42161, "weETH"),
        ("renzo", 8453, "ezETH"),
        ("kelp", 1, "rsETH"),
    ],
)
def test_symbol_per_chain(protocol, chain_id, expected_symbol):
    entry = lst_for_chain(protocol, chain_id)
    assert entry is not None, f"{protocol}/{chain_id} missing"
    assert entry["symbol"] == expected_symbol


def test_lst_for_chain_empty_protocol_returns_none():
    assert lst_for_chain("", 1) is None
    assert lst_for_chain(None, 1) is None  # type: ignore[arg-type]
