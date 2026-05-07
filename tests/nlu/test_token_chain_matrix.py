"""Token × chain combinatorial matrix.

For every supported (token, chain) pair, assert validation routes the swap
correctly:
- Same-chain swaps (token A on chain C, token B on chain C) → ok.
- Cross-chain (token A on chain C1, token B not on C1) → cross_chain.
- Token not on chain (chain C1 doesn't host token) → token_not_on_chain.

Catches: WETH-on-Solana misroutes, BSC USDC vs ETH USDC confusion, etc.
"""
from __future__ import annotations

from itertools import combinations

import pytest

from src.agent.intent.validation import (
    TOKEN_CHAINS,
    is_cross_chain,
    primary_home_chain,
    token_supported_on_chain,
    validate_swap_params,
)


_SUPPORTED_CHAINS = sorted({c for chains in TOKEN_CHAINS.values() for c in chains})
_AMOUNT_OK = "1000000"


def _matrix_pairs():
    """Yield (token_a, token_b, chain_id) for every interesting combination."""
    tokens = sorted(TOKEN_CHAINS.keys())
    for a, b in combinations(tokens, 2):
        for cid in _SUPPORTED_CHAINS:
            yield a, b, cid


@pytest.mark.parametrize("token_a,token_b,chain_id", list(_matrix_pairs()))
def test_token_pair_on_chain(token_a: str, token_b: str, chain_id: int) -> None:
    a_ok = token_supported_on_chain(token_a, chain_id)
    b_ok = token_supported_on_chain(token_b, chain_id)
    v = validate_swap_params(
        token_in=token_a, token_out=token_b,
        chain_id=chain_id, amount_in=_AMOUNT_OK,
    )

    if a_ok and b_ok:
        # Both supported on this chain → swap accepted.
        assert v.ok, f"{token_a}->{token_b} on {chain_id} should be ok: {v.error_code}"
        return

    # At least one isn't on the chain — must reject.
    assert not v.ok, f"{token_a}->{token_b} on {chain_id} should be rejected"
    assert v.error_code in {"cross_chain", "token_not_on_chain"}


def test_primary_home_chain_picks_canonical():
    # Single-home tokens
    assert primary_home_chain("SOL") == 101
    assert primary_home_chain("BNB") == 56
    assert primary_home_chain("AVAX") == 43114
    # Multi-home — preference picks ethereum mainnet
    assert primary_home_chain("ETH") == 1
    assert primary_home_chain("WETH") == 1
    assert primary_home_chain("USDC") == 1


def test_cross_chain_classic_pairs():
    # SOL-side meme to EVM should always be cross-chain on Solana
    assert is_cross_chain("BONK", "WETH", 101)
    assert is_cross_chain("WIF", "ETH", 101)
    # BNB cross-Solana
    assert is_cross_chain("BNB", "SOL", 56)
    assert is_cross_chain("SOL", "BNB", 101)
    # Same-chain pairs are NOT cross-chain
    assert not is_cross_chain("USDC", "WETH", 1)
    assert not is_cross_chain("BONK", "SOL", 101)
