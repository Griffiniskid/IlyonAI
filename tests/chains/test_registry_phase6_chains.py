"""Pin test for Phase C P1-C-004 fix — ChainRegistry must initialize all
17 EVM chains, not just the original 7.

Pre-fix: ChainRegistry.initialize() rpc_mapping only included
ETHEREUM/BASE/ARBITRUM/BSC/POLYGON/OPTIMISM/AVALANCHE → any caller
doing get_config(ChainType.LINEA) raised
ValueError("Chain 'linea' is not configured").
Post-fix: rpc_mapping covers the 10 Phase-6 chains too (Linea, Scroll,
Mantle, Blast, zkSync, Gnosis, Celo, Sonic, Berachain, Unichain).

Asserts:
 1. All 17 EVM + Solana chains resolvable via get_config()
 2. RPC URL is None (env var unset in test env) — but the ChainConfig
    object exists with EVM_CHAIN_CONFIGS metadata (explorer_url,
    primary_dex, etc.)
"""
from __future__ import annotations

import pytest

from src.chains.base import ChainType
from src.chains.registry import ChainRegistry
from src.config import settings


PHASE_6_CHAINS = [
    ChainType.LINEA, ChainType.SCROLL, ChainType.MANTLE, ChainType.BLAST,
    ChainType.ZKSYNC, ChainType.GNOSIS, ChainType.CELO, ChainType.SONIC,
    ChainType.BERACHAIN, ChainType.UNICHAIN,
]


@pytest.fixture
def initialized_registry():
    r = ChainRegistry.get_instance()
    r.initialize(settings)
    return r


def test_phase6_chains_resolvable(initialized_registry):
    """All 10 Phase-6 chains must be in the registry post-init."""
    for ct in PHASE_6_CHAINS:
        cfg = initialized_registry.get_config(ct)
        assert cfg is not None
        assert cfg.chain_type == ct
        # explorer_url is set from EVM_CHAIN_CONFIGS even when rpc_url is None
        assert isinstance(cfg.explorer_url, str)


def test_total_config_count_at_least_17_evm_plus_solana(initialized_registry):
    """Spec mandates 17 EVM + Solana chains."""
    assert len(initialized_registry._configs) >= 18, (
        f"expected ≥18 (17 EVM + Solana), got {len(initialized_registry._configs)}: "
        f"{[c.value for c in initialized_registry._configs.keys()]}"
    )
