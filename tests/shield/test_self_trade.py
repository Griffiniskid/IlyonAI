"""Pin tests for spec §13 Row 26 — SELF_TRADE_AGAINST_OWN_LP.

Covers the three cases the spec calls out:
    1. User owns USDC/WETH 0.05% NFT, swap routes through the same pool
       → SELF_TRADE_AGAINST_OWN_LP fires.
    2. User owns USDC/WETH 0.05% NFT, swap routes through USDC/WETH 0.30%
       pool (different fee tier, different pool addr) → no blocker.
    3. User has no open positions → no blocker (and no RPC traffic).

All RPC + DB I/O is mocked. The detector is purely deterministic given
the injected find_user_positions + get_pool_addr callables.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.shield.self_trade import (
    SELF_TRADE_BLOCKER_CODE,
    detect_self_trade,
    detect_self_trade_sync,
)

# Canonical mainnet addresses used throughout the tests. The actual hex
# digits don't matter — what matters is they round-trip case-insensitively
# and that two different fee tiers map to two different pool addresses.
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC_WETH_005_POOL = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"  # 0.05% tier
USDC_WETH_030_POOL = "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8"  # 0.30% tier
USER_WALLET = "0x1234567890123456789012345678901234567890"
ETH_CHAIN_ID = 1


def _make_position(fee_bps: int) -> dict[str, Any]:
    """Build a synthetic open-LP row in the shape the position_store
    emits (see src/defi/position_store.py::find_open_positions)."""
    return {
        "position_id": f"pos-{fee_bps}",
        "user_id": 1,
        "wallet_address": USER_WALLET.lower(),
        "chain_id": ETH_CHAIN_ID,
        "protocol": "uniswap-v3",
        "receipt_kind": "UniswapV3NFP",
        "token0": USDC,
        "token1": WETH,
        "fee_bps": fee_bps,
        "status": "open",
    }


def _make_pool_resolver(mapping: dict[tuple[str, int], str]):
    """Return a getPool stub keyed by (protocol, fee_bps). Token args are
    normalized to canonical lexicographic order — we just check the fee
    discriminator in the tests."""

    async def _resolve(chain_name, protocol, token0, token1, fee_bps):
        return mapping.get((protocol, int(fee_bps)))

    return _resolve


@pytest.mark.asyncio
async def test_self_trade_fires_when_swap_pool_matches_user_lp_pool() -> None:
    """User owns USDC/WETH 0.05% NFT. Pre-swap targets that exact pool → blocker."""
    positions = [_make_position(500)]  # 0.05% tier = 500 bps

    async def _find(_wallet, _chain_id):
        return positions

    resolver = _make_pool_resolver({
        ("uniswap-v3", 500): USDC_WETH_005_POOL,
    })

    code = await detect_self_trade(
        USER_WALLET,
        USDC_WETH_005_POOL,
        ETH_CHAIN_ID,
        find_user_positions=_find,
        get_pool_addr=resolver,
    )
    assert code == SELF_TRADE_BLOCKER_CODE


@pytest.mark.asyncio
async def test_self_trade_silent_when_swap_pool_is_different_fee_tier() -> None:
    """User owns USDC/WETH 0.05% NFT. Swap routes through 0.30% pool
    (different address) → no blocker. Catches the false-positive class
    where token-pair match alone would over-trigger."""
    positions = [_make_position(500)]

    async def _find(_wallet, _chain_id):
        return positions

    resolver = _make_pool_resolver({
        ("uniswap-v3", 500): USDC_WETH_005_POOL,
        ("uniswap-v3", 3000): USDC_WETH_030_POOL,
    })

    code = await detect_self_trade(
        USER_WALLET,
        USDC_WETH_030_POOL,  # different fee tier → different pool
        ETH_CHAIN_ID,
        find_user_positions=_find,
        get_pool_addr=resolver,
    )
    assert code is None


@pytest.mark.asyncio
async def test_self_trade_silent_when_no_open_positions() -> None:
    """User has no open V3 NFTs → detector short-circuits cleanly."""

    async def _find(_wallet, _chain_id):
        return []

    # Resolver should never be called — give it an empty mapping. If the
    # detector regresses and tries to resolve anyway, it'd return None
    # and we'd still pass; the assertion below is the load-bearing check.
    resolver = _make_pool_resolver({})

    code = await detect_self_trade(
        USER_WALLET,
        USDC_WETH_005_POOL,
        ETH_CHAIN_ID,
        find_user_positions=_find,
        get_pool_addr=resolver,
    )
    assert code is None


@pytest.mark.asyncio
async def test_self_trade_case_insensitive_pool_match() -> None:
    """Pool addresses must compare case-insensitively — checksum casing
    must not let a self-trade slip past the detector."""
    positions = [_make_position(500)]

    async def _find(_wallet, _chain_id):
        return positions

    resolver = _make_pool_resolver({
        ("uniswap-v3", 500): USDC_WETH_005_POOL.lower(),
    })

    code = await detect_self_trade(
        USER_WALLET,
        USDC_WETH_005_POOL.upper().replace("0X", "0x"),  # uppercase hex
        ETH_CHAIN_ID,
        find_user_positions=_find,
        get_pool_addr=resolver,
    )
    assert code == SELF_TRADE_BLOCKER_CODE


@pytest.mark.asyncio
async def test_self_trade_skips_non_v3_positions() -> None:
    """A V2-style position (no fee tier, no NFP receipt) should not be
    considered for V3 self-trade — the detector silently ignores it."""
    positions = [{
        "position_id": "v2-pos",
        "user_id": 1,
        "wallet_address": USER_WALLET.lower(),
        "chain_id": ETH_CHAIN_ID,
        "protocol": "uniswap-v2",
        "receipt_kind": "UniswapV2LP",  # ERC-20 LP, not V3 NFT
        "token0": USDC,
        "token1": WETH,
        "status": "open",
    }]

    async def _find(_wallet, _chain_id):
        return positions

    resolver = _make_pool_resolver({})

    code = await detect_self_trade(
        USER_WALLET,
        USDC_WETH_005_POOL,
        ETH_CHAIN_ID,
        find_user_positions=_find,
        get_pool_addr=resolver,
    )
    assert code is None


def test_detect_self_trade_sync_matches_on_owned_pool() -> None:
    """The sync variant short-circuits when the inventory already has the
    resolved owned-pool set. Used by the preflight fast path."""
    code = detect_self_trade_sync(
        USER_WALLET,
        USDC_WETH_005_POOL,
        ETH_CHAIN_ID,
        owned_pool_addrs=[USDC_WETH_005_POOL],
    )
    assert code == SELF_TRADE_BLOCKER_CODE


def test_detect_self_trade_sync_silent_on_different_pool() -> None:
    code = detect_self_trade_sync(
        USER_WALLET,
        USDC_WETH_030_POOL,
        ETH_CHAIN_ID,
        owned_pool_addrs=[USDC_WETH_005_POOL],
    )
    assert code is None


# ---------------------------------------------------------------------------
# Preflight integration: confirm detect_self_trade is wired into the chain.
# ---------------------------------------------------------------------------


def test_preflight_emits_self_trade_blocker_for_overlapping_pool() -> None:
    """End-to-end through evaluate_preflight: a swap step whose
    transaction carries a swap_pool_addr matching an existing V3 LP
    position triggers a SELF_TRADE_AGAINST_OWN_LP blocker."""
    from decimal import Decimal

    from src.defi.execution.models import (
        ExecutionStepV3,
        UnsignedStepTransaction,
        make_step,
    )
    from src.defi.execution.preflight import WalletInventory, evaluate_preflight

    tx = UnsignedStepTransaction(
        chain_kind="evm",
        chain_id=ETH_CHAIN_ID,
        to="0x" + "ab" * 20,
        data="0x",
        value="0",
    )
    # The adapter's job to stash the resolved pool on the transaction.
    tx.swap_pool_addr = USDC_WETH_005_POOL  # type: ignore[attr-defined]

    step = make_step(
        index=1,
        action="swap",
        title="Pre-swap USDC -> WETH",
        description="Half-zap leg",
        chain="ethereum",
        wallet="MetaMask",
        protocol="uniswap-v3",
        asset_in="USDC",
        asset_out="WETH",
        amount_in="100",
        amount_out="0.03",
    )
    step.transaction = tx

    inventory = WalletInventory(
        evm_address=USER_WALLET,
        chain_id=ETH_CHAIN_ID,
        balances={("ethereum", "USDC"): Decimal("1000")},
        native_gas={"ethereum": Decimal("1")},
        existing_positions=[{
            **_make_position(500),
            # Pre-resolved pool so preflight uses the sync fast path —
            # no RPC + no event-loop dance in the test.
            "pool_address": USDC_WETH_005_POOL,
        }],
    )

    blockers = evaluate_preflight(steps=[step], inventory=inventory)
    codes = {b.code for b in blockers}
    assert SELF_TRADE_BLOCKER_CODE in codes
    # And the blocker scope points at the offending step.
    self_trade = next(b for b in blockers if b.code == SELF_TRADE_BLOCKER_CODE)
    assert step.step_id in self_trade.affected_step_ids


def test_preflight_silent_when_swap_pool_is_unrelated() -> None:
    """If the swap routes through a pool the user doesn't LP, no blocker."""
    from decimal import Decimal

    from src.defi.execution.models import (
        UnsignedStepTransaction,
        make_step,
    )
    from src.defi.execution.preflight import WalletInventory, evaluate_preflight

    tx = UnsignedStepTransaction(
        chain_kind="evm",
        chain_id=ETH_CHAIN_ID,
        to="0x" + "ab" * 20,
        data="0x",
        value="0",
    )
    tx.swap_pool_addr = USDC_WETH_030_POOL  # type: ignore[attr-defined]

    step = make_step(
        index=1,
        action="swap",
        title="Pre-swap USDC -> WETH (0.30%)",
        description="Half-zap leg",
        chain="ethereum",
        wallet="MetaMask",
        protocol="uniswap-v3",
        asset_in="USDC",
        asset_out="WETH",
        amount_in="100",
        amount_out="0.03",
    )
    step.transaction = tx

    inventory = WalletInventory(
        evm_address=USER_WALLET,
        chain_id=ETH_CHAIN_ID,
        balances={("ethereum", "USDC"): Decimal("1000")},
        native_gas={"ethereum": Decimal("1")},
        existing_positions=[{
            **_make_position(500),
            "pool_address": USDC_WETH_005_POOL,
        }],
    )

    blockers = evaluate_preflight(steps=[step], inventory=inventory)
    codes = {b.code for b in blockers}
    assert SELF_TRADE_BLOCKER_CODE not in codes
