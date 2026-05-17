"""Pin tests for spec §13 Row 17 — JIT_ATTACK_ADJACENCY.

Covers the four cases the spec calls out for the JIT mempool monitor:
    1. Monitor has a >$100k pending swap targeting the LP's pool
       → JIT_ATTACK_ADJACENCY fires.
    2. Monitor has only small (<$100k) pending swaps
       → no blocker (threshold guard).
    3. Monitor has a >$100k pending swap but it targets a DIFFERENT pool
       → no blocker (pool-key guard).
    4. Monitor instance exists but has not been started yet
       → check returns None (fail-soft, no false positives).

All WS I/O is mocked — the JitMonitor is constructed directly and the
pending-tx ring buffer is populated via push_pending(). No real socket
is opened in this test suite.
"""
from __future__ import annotations

import pytest

from src.shield.jit_monitor import (
    JIT_BLOCKER_CODE,
    JitMonitor,
    PendingSwap,
    check_jit_adjacency,
    check_jit_adjacency_sync,
)

# Canonical-looking pool addresses. The actual hex digits don't matter —
# the load-bearing property is that TARGET_POOL and OTHER_POOL are
# different so the pool-key guard test is meaningful.
TARGET_POOL = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"  # USDC/WETH 0.05%
OTHER_POOL = "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8"  # USDC/WETH 0.30%


def _norm(addr: str) -> str:
    return addr.lower()


@pytest.mark.asyncio
async def test_jit_fires_when_200k_swap_queued_on_same_pool() -> None:
    """Monitor sees a $200k pending swap targeting TARGET_POOL → blocker."""
    monitor = JitMonitor()
    await monitor.start(rpc_ws_url=None)  # offline mode — no WS opened
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=200_000.0,
        tx_hash="0xdead",
    ))

    code = await check_jit_adjacency(TARGET_POOL, monitor=monitor)
    assert code == JIT_BLOCKER_CODE

    await monitor.stop()


@pytest.mark.asyncio
async def test_jit_silent_when_only_small_swaps_pending() -> None:
    """Monitor sees only $50k swaps → below default $100k threshold,
    so no blocker. Catches the false-positive class where any
    pool-targeting swap would over-trigger."""
    monitor = JitMonitor()
    await monitor.start(rpc_ws_url=None)
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=50_000.0,
        tx_hash="0xbeef",
    ))
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=25_000.0,
        tx_hash="0xcafe",
    ))

    code = await check_jit_adjacency(TARGET_POOL, monitor=monitor)
    assert code is None

    await monitor.stop()


@pytest.mark.asyncio
async def test_jit_silent_when_200k_swap_targets_different_pool() -> None:
    """Monitor sees a $200k swap, but it targets OTHER_POOL. The user's
    LP is on TARGET_POOL → no blocker (pool-key guard prevents false
    positives across uncorrelated pools)."""
    monitor = JitMonitor()
    await monitor.start(rpc_ws_url=None)
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(OTHER_POOL),
        notional_usd=200_000.0,
        tx_hash="0xfeed",
    ))

    code = await check_jit_adjacency(TARGET_POOL, monitor=monitor)
    assert code is None

    await monitor.stop()


@pytest.mark.asyncio
async def test_jit_returns_none_when_monitor_not_started() -> None:
    """Monitor instance exists but start() hasn't been awaited → check
    returns None silently. This is the load-bearing fail-soft contract:
    a misconfigured monitor must NEVER produce a false-positive blocker
    that prevents a user from signing."""
    monitor = JitMonitor()
    # NOTE: deliberately NOT calling start(). Even with a $200k swap
    # pushed (which push_pending will drop because not started), the
    # check must return None.
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=200_000.0,
        tx_hash="0xface",
    ))
    assert monitor.started is False

    code = await check_jit_adjacency(TARGET_POOL, monitor=monitor)
    assert code is None


@pytest.mark.asyncio
async def test_jit_returns_none_when_monitor_is_none() -> None:
    """Caller omits the monitor entirely (no mempool layer wired) →
    check returns None. The detector must be fully opt-in."""
    code = await check_jit_adjacency(TARGET_POOL, monitor=None)
    assert code is None


@pytest.mark.asyncio
async def test_jit_case_insensitive_pool_match() -> None:
    """Pool addresses must compare case-insensitively. Mixed-case
    checksum casing on either side must not let a JIT slip past."""
    monitor = JitMonitor()
    await monitor.start(rpc_ws_url=None)
    # Push lowercased, query uppercased.
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=150_000.0,
    ))
    code = await check_jit_adjacency(
        TARGET_POOL.upper().replace("0X", "0x"),
        monitor=monitor,
    )
    assert code == JIT_BLOCKER_CODE
    await monitor.stop()


@pytest.mark.asyncio
async def test_jit_custom_threshold_overrides_default() -> None:
    """Caller-supplied threshold short-circuits the $100k default. Lets
    risk-tier consumers tune the trigger per chain / per-pool TVL."""
    monitor = JitMonitor()
    await monitor.start(rpc_ws_url=None)
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=60_000.0,
    ))
    # Default would not fire; explicit $50k threshold does.
    code = await check_jit_adjacency(
        TARGET_POOL,
        threshold_usd=50_000.0,
        monitor=monitor,
    )
    assert code == JIT_BLOCKER_CODE
    await monitor.stop()


@pytest.mark.asyncio
async def test_jit_picks_max_notional_across_multiple_legs() -> None:
    """When a pool has multiple pending swaps, the check uses the worst-
    case notional (max), not the sum or the average."""
    monitor = JitMonitor()
    await monitor.start(rpc_ws_url=None)
    # Three legs against the same pool. The $250k one is the threat.
    for n in (20_000.0, 40_000.0, 250_000.0):
        monitor.push_pending(PendingSwap(
            pool_addr=_norm(TARGET_POOL),
            notional_usd=n,
        ))
    notional = monitor.get_adjacent_swap_usd(TARGET_POOL)
    assert notional == 250_000.0
    code = await check_jit_adjacency(TARGET_POOL, monitor=monitor)
    assert code == JIT_BLOCKER_CODE
    await monitor.stop()


def test_jit_sync_variant_matches_async() -> None:
    """The sync variant exists so preflight (which is sync) doesn't need
    an event-loop dance. Must agree with the async variant on the same
    monitor state."""
    import asyncio as _asyncio

    monitor = JitMonitor()
    _asyncio.run(monitor.start(rpc_ws_url=None))
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=150_000.0,
    ))
    code = check_jit_adjacency_sync(TARGET_POOL, monitor=monitor)
    assert code == JIT_BLOCKER_CODE

    code_other = check_jit_adjacency_sync(OTHER_POOL, monitor=monitor)
    assert code_other is None

    _asyncio.run(monitor.stop())


# ---------------------------------------------------------------------------
# Preflight integration: confirm check_jit_adjacency is wired into the chain.
# ---------------------------------------------------------------------------


def test_preflight_emits_jit_blocker_for_lp_step_against_threatened_pool() -> None:
    """End-to-end through evaluate_preflight: a deposit_lp step whose
    transaction carries lp_pool_addr matching a >$100k pending swap in
    the monitor triggers a JIT_ATTACK_ADJACENCY blocker."""
    import asyncio as _asyncio
    from decimal import Decimal

    from src.defi.execution.models import (
        UnsignedStepTransaction,
        make_step,
    )
    from src.defi.execution.preflight import WalletInventory, evaluate_preflight

    monitor = JitMonitor()
    _asyncio.run(monitor.start(rpc_ws_url=None))
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=300_000.0,
        tx_hash="0xabc",
    ))

    tx = UnsignedStepTransaction(
        chain_kind="evm",
        chain_id=1,
        to="0x" + "ab" * 20,
        data="0x",
        value="0",
    )
    # Adapter stamps the resolved pool on the transaction.
    tx.lp_pool_addr = TARGET_POOL  # type: ignore[attr-defined]

    step = make_step(
        index=1,
        action="deposit_lp",
        title="Add USDC/WETH LP",
        description="Concentrated V3 mint",
        chain="ethereum",
        wallet="MetaMask",
        protocol="uniswap-v3",
        asset_in="USDC",
        asset_out="WETH",
        amount_in="50000",
        amount_out="15",
    )
    step.transaction = tx

    inventory = WalletInventory(
        evm_address="0x" + "1" * 40,
        chain_id=1,
        balances={("ethereum", "USDC"): Decimal("100000")},
        native_gas={"ethereum": Decimal("1")},
        jit_monitor=monitor,
    )

    blockers = evaluate_preflight(steps=[step], inventory=inventory)
    codes = {b.code for b in blockers}
    assert JIT_BLOCKER_CODE in codes

    jit = next(b for b in blockers if b.code == JIT_BLOCKER_CODE)
    assert step.step_id in jit.affected_step_ids

    _asyncio.run(monitor.stop())


def test_preflight_silent_when_no_monitor_attached() -> None:
    """No JitMonitor on inventory → no JIT blocker fires, even on an LP
    step. Confirms the fail-soft contract through the preflight layer."""
    from decimal import Decimal

    from src.defi.execution.models import (
        UnsignedStepTransaction,
        make_step,
    )
    from src.defi.execution.preflight import WalletInventory, evaluate_preflight

    tx = UnsignedStepTransaction(
        chain_kind="evm",
        chain_id=1,
        to="0x" + "ab" * 20,
        data="0x",
        value="0",
    )
    tx.lp_pool_addr = TARGET_POOL  # type: ignore[attr-defined]

    step = make_step(
        index=1,
        action="deposit_lp",
        title="Add USDC/WETH LP",
        description="Concentrated V3 mint",
        chain="ethereum",
        wallet="MetaMask",
        protocol="uniswap-v3",
        asset_in="USDC",
        asset_out="WETH",
        amount_in="50000",
        amount_out="15",
    )
    step.transaction = tx

    inventory = WalletInventory(
        evm_address="0x" + "1" * 40,
        chain_id=1,
        balances={("ethereum", "USDC"): Decimal("100000")},
        native_gas={"ethereum": Decimal("1")},
        # jit_monitor deliberately omitted.
    )

    blockers = evaluate_preflight(steps=[step], inventory=inventory)
    codes = {b.code for b in blockers}
    assert JIT_BLOCKER_CODE not in codes


def test_preflight_silent_for_non_lp_steps_even_with_monitor() -> None:
    """A bare swap step (not deposit_lp) must NOT trigger JIT adjacency —
    JIT is an LP-add concern. The self-trade detector handles swap legs."""
    import asyncio as _asyncio
    from decimal import Decimal

    from src.defi.execution.models import (
        UnsignedStepTransaction,
        make_step,
    )
    from src.defi.execution.preflight import WalletInventory, evaluate_preflight

    monitor = JitMonitor()
    _asyncio.run(monitor.start(rpc_ws_url=None))
    monitor.push_pending(PendingSwap(
        pool_addr=_norm(TARGET_POOL),
        notional_usd=300_000.0,
    ))

    tx = UnsignedStepTransaction(
        chain_kind="evm",
        chain_id=1,
        to="0x" + "ab" * 20,
        data="0x",
        value="0",
    )
    tx.swap_pool_addr = TARGET_POOL  # type: ignore[attr-defined]

    step = make_step(
        index=1,
        action="swap",
        title="USDC -> WETH",
        description="Pre-zap swap",
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
        evm_address="0x" + "1" * 40,
        chain_id=1,
        balances={("ethereum", "USDC"): Decimal("1000")},
        native_gas={"ethereum": Decimal("1")},
        jit_monitor=monitor,
    )

    blockers = evaluate_preflight(steps=[step], inventory=inventory)
    codes = {b.code for b in blockers}
    assert JIT_BLOCKER_CODE not in codes

    _asyncio.run(monitor.stop())
