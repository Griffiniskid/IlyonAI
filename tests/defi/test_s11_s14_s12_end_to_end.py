"""V7-002 §7 S11/S14/S12 end-to-end pin tests.

Closes the detector → adapter break for refinance (S11), V2→V3 migrate
(S14), and claim-and-compound (S12). Each test:

1. Asserts the capability registry accepts the detector-emitted action on
   the relevant (chain, protocol) tuple — proving the adapter `actions`
   frozenset was extended.
2. Drives the bundler/composer and asserts the returned ExecutionStepV3
   list shape (count + per-step action) + the depends_on chain.

No live RPC is touched; the bundler/composer are calldata-free.
"""
from __future__ import annotations

import pytest

from src.defi.execution.adapters.claim_compound_composer import (
    ClaimCompoundComposer,
)
from src.defi.execution.adapters.multicall_bundler import (
    MulticallBundler,
    PositionRef,
)
from src.defi.execution.capabilities import build_default_registry


# ---------------------------------------------------------------------------
# §7 S11 — refinance: same-protocol V3 NFT range rebalance.
# ---------------------------------------------------------------------------
def test_s11_refinance_capability_gate_and_bundler_shape():
    """Detector emits action='refinance'; V3 NFT adapter must accept it.

    Bundler returns 3 ordered steps:
      [decrease_liquidity-ish, collect-ish, add_liquidity]
    depends_on wires step1->step0, step2->step1 so the V3 mint cannot fire
    before the unwind confirms.
    """
    registry = build_default_registry()

    # Capability gate accepts 'refinance' on uniswap-v3 (V3 NFT adapter).
    verdict = registry.find(
        chain="ethereum", protocol="uniswap-v3", action="refinance"
    )
    assert verdict.supported, f"V3 NFT adapter must accept refinance: {verdict.reason}"
    assert verdict.adapter_id == "uniswap-v3-nft"

    bundler = MulticallBundler()
    old = PositionRef(
        chain="ethereum",
        protocol="uniswap-v3",
        pool_symbol="USDC-WETH",
        token_a="USDC",
        token_b="WETH",
        token_id=123456,
        range_kind="narrow",
    )
    new = PositionRef(
        chain="ethereum",
        protocol="uniswap-v3",  # same protocol — refinance
        pool_symbol="USDC-WETH",
        token_a="USDC",
        token_b="WETH",
        range_lower=2800.0,
        range_upper=3200.0,
        range_kind="tight",
    )
    steps = bundler.build_refinance(old, new)

    assert len(steps) == 3, "refinance must collapse to exactly 3 ExecutionStepV3"
    # Step 0 unwinds; step 1 collects; step 2 mints fresh range.
    assert steps[0].action == "withdraw"          # V3 decreaseLiquidity alias
    assert steps[1].action == "claim_rewards"     # V3 collect alias
    assert steps[2].action == "deposit_lp"
    # Same protocol throughout — refinance is a same-pool rebalance.
    assert steps[0].protocol == steps[2].protocol == "uniswap-v3"
    # Dependency chain: step N depends on step N-1.
    assert steps[1].depends_on == [steps[0].step_id]
    assert steps[2].depends_on == [steps[1].step_id]
    assert steps[0].depends_on == []  # head of the chain

    # Step indices are 0,1,2 in order.
    assert [s.index for s in steps] == [0, 1, 2]


def test_s11_refinance_rejects_cross_protocol():
    """Refinance is same-protocol only; cross-protocol must raise."""
    bundler = MulticallBundler()
    old = PositionRef(
        chain="ethereum", protocol="uniswap-v3", pool_symbol="USDC-WETH",
        token_a="USDC", token_b="WETH", token_id=1,
    )
    new = PositionRef(
        chain="ethereum", protocol="pancakeswap-v3", pool_symbol="USDC-WETH",
        token_a="USDC", token_b="WETH",
    )
    with pytest.raises(ValueError, match="same-protocol"):
        bundler.build_refinance(old, new)


# ---------------------------------------------------------------------------
# §7 S14 — migrate: cross-protocol V2 → V3.
# ---------------------------------------------------------------------------
def test_s14_migrate_capability_gate_and_bundler_shape():
    """Detector emits action='migrate'; both legs of the registry accept it.

    V2 leg lands on UniswapV2DualTokenAdapter; the V3 mint lands on
    UniswapV3NFTAdapter. Bundler returns 3 steps with the cross-protocol
    split honoured.
    """
    registry = build_default_registry()

    # V2 side — remove_liquidity leg.
    v2_verdict = registry.find(
        chain="ethereum", protocol="uniswap-v2", action="migrate"
    )
    assert v2_verdict.supported, f"V2 adapter must accept migrate: {v2_verdict.reason}"
    assert v2_verdict.adapter_id == "uniswap-v2-dual-token"

    # V3 side — fresh NFT mint leg.
    v3_verdict = registry.find(
        chain="ethereum", protocol="uniswap-v3", action="migrate"
    )
    assert v3_verdict.supported, f"V3 NFT adapter must accept migrate: {v3_verdict.reason}"
    assert v3_verdict.adapter_id == "uniswap-v3-nft"

    bundler = MulticallBundler()
    old = PositionRef(
        chain="ethereum",
        protocol="uniswap-v2",
        pool_symbol="USDC-WETH",
        token_a="USDC",
        token_b="WETH",
        pool_address="0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
    )
    new = PositionRef(
        chain="ethereum",
        protocol="uniswap-v3",
        pool_symbol="USDC-WETH",
        token_a="USDC",
        token_b="WETH",
        range_lower=2900.0,
        range_upper=3100.0,
    )
    steps = bundler.build_migrate(old, new)

    assert len(steps) == 3, "migrate must collapse to exactly 3 ExecutionStepV3"
    # Step 0 unwinds on V2; step 1 settles; step 2 mints V3 NFT.
    assert steps[0].action == "withdraw"
    assert steps[1].action == "verify_balance"
    assert steps[2].action == "deposit_lp"
    # Cross-protocol split: step 0 on V2, steps 1+2 on V3.
    assert steps[0].protocol == "uniswap-v2"
    assert steps[1].protocol == "uniswap-v3"
    assert steps[2].protocol == "uniswap-v3"
    # Dependency chain holds.
    assert steps[1].depends_on == [steps[0].step_id]
    assert steps[2].depends_on == [steps[1].step_id]


def test_s14_migrate_rejects_same_protocol():
    """Migrate is cross-protocol only; same-protocol must raise."""
    bundler = MulticallBundler()
    old = PositionRef(
        chain="ethereum", protocol="uniswap-v2", pool_symbol="USDC-WETH",
        token_a="USDC", token_b="WETH",
    )
    new = PositionRef(
        chain="ethereum", protocol="uniswap-v2", pool_symbol="USDC-WETH",
        token_a="USDC", token_b="WETH",
    )
    with pytest.raises(ValueError, match="cross-protocol"):
        bundler.build_migrate(old, new)


# ---------------------------------------------------------------------------
# §7 S12 — claim_compound: claim accrued rewards + re-supply.
# ---------------------------------------------------------------------------
def test_s12_claim_compound_capability_gate_and_composer_shape():
    """Detector emits action='claim_compound'; aave-v3 adapter accepts it.

    Composer returns 2 ordered steps: [claim_rewards, supply], with the
    supply leg depending on the claim leg so the re-supply never fires
    before the rewards land in the wallet.
    """
    registry = build_default_registry()

    # Aave V3 supply adapter must whitelist 'claim_compound'.
    aave_verdict = registry.find(
        chain="ethereum", protocol="aave-v3", action="claim_compound"
    )
    assert aave_verdict.supported, (
        f"Aave V3 adapter must accept claim_compound: {aave_verdict.reason}"
    )
    assert aave_verdict.adapter_id == "aave-v3-supply"

    # Compound V3 adapter also accepts claim_compound (COMP re-supply loop).
    comp_verdict = registry.find(
        chain="ethereum", protocol="compound-v3", action="claim_compound"
    )
    assert comp_verdict.supported, (
        f"Compound V3 adapter must accept claim_compound: {comp_verdict.reason}"
    )
    assert comp_verdict.adapter_id == "compound-v3-supply"

    composer = ClaimCompoundComposer()
    action_spec = {
        "chain": "ethereum",
        "protocol": "aave-v3",
        "asset_in": "AAVE",
        "extra": {
            "reward_token": "AAVE",
            "stake_target": "aave-v3",
        },
    }
    steps = composer.build(action_spec)

    assert len(steps) == 2, "claim_compound must collapse to exactly 2 ExecutionStepV3"
    # Step 0 claims rewards; step 1 supplies them back.
    assert steps[0].action == "claim_rewards"
    assert steps[1].action == "supply"
    # Same chain, both EVM (MetaMask).
    assert steps[0].chain == steps[1].chain == "ethereum"
    assert steps[0].wallet == steps[1].wallet == "MetaMask"
    # Reward token threaded through both legs.
    assert steps[0].asset_in == "AAVE"
    assert steps[1].asset_in == "AAVE"
    # Dependency: supply waits on claim receipt.
    assert steps[1].depends_on == [steps[0].step_id]
    assert steps[0].depends_on == []


def test_s12_claim_compound_stake_target_override():
    """When extra.stake_target overrides the source, step 1 routes there."""
    composer = ClaimCompoundComposer()
    action_spec = {
        "chain": "ethereum",
        "protocol": "aave-v3",
        "asset_in": "AAVE",
        "extra": {
            "reward_token": "AAVE",
            "stake_target": "stkaave",  # stake into staking module, not lending pool
        },
    }
    steps = composer.build(action_spec)
    assert len(steps) == 2
    assert steps[0].protocol == "aave-v3"
    assert steps[1].protocol == "stkaave"


def test_s12_claim_compound_missing_reward_token_raises():
    """Composer must refuse to build when reward_token is missing."""
    composer = ClaimCompoundComposer()
    with pytest.raises(ValueError, match="reward_token"):
        composer.build({"chain": "ethereum", "protocol": "aave-v3", "extra": {}})
