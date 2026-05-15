"""Chain expansion regression — R7 Phase 6 8→18 EVM chains.

Pins ChainType enum + chain_id map + native_token_symbol so the new
chains can't silently regress.
"""
from __future__ import annotations

from src.chains.base import ChainType


def test_resume_v2_chain_set_present():
    expected_new = (
        "linea", "scroll", "mantle", "blast", "zksync",
        "gnosis", "celo", "sonic", "berachain", "unichain",
    )
    values = {ct.value for ct in ChainType}
    for chain in expected_new:
        assert chain in values, f"chain {chain} missing from ChainType"


def test_chain_ids_match_spec():
    """Pin every Phase 6 chain to its canonical chainId. Drift would
    silently break any cross-chain composed plan."""
    expected = {
        "linea": 59144,
        "scroll": 534352,
        "mantle": 5000,
        "blast": 81457,
        "zksync": 324,
        "gnosis": 100,
        "celo": 42220,
        "sonic": 146,
        "berachain": 80094,
        "unichain": 130,
    }
    for value, chain_id in expected.items():
        ct = ChainType(value)
        assert ct.chain_id == chain_id, f"{value} chain_id mismatch: expected {chain_id}, got {ct.chain_id}"


def test_native_tokens_match_spec():
    expected = {
        "linea": "ETH",
        "scroll": "ETH",
        "mantle": "MNT",
        "blast": "ETH",
        "zksync": "ETH",
        "gnosis": "xDAI",
        "celo": "CELO",
        "sonic": "S",
        "berachain": "BERA",
        "unichain": "ETH",
    }
    for value, sym in expected.items():
        ct = ChainType(value)
        assert ct.native_token_symbol == sym, f"{value} native_token_symbol mismatch"


def test_evm_chains_all_have_evm_flag():
    for value in (
        "linea", "scroll", "mantle", "blast", "zksync",
        "gnosis", "celo", "sonic", "berachain", "unichain",
    ):
        assert ChainType(value).is_evm is True
