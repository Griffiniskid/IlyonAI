"""Wallet preflight: verify balance, gas, allowance, wallet kind before signing."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from src.defi.execution.models import ExecutionBlocker, ExecutionStepV3

logger = logging.getLogger(__name__)


@dataclass
class WalletInventory:
    evm_address: str | None = None
    solana_address: str | None = None
    chain_id: int | None = None
    balances: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    native_gas: dict[str, Decimal] = field(default_factory=dict)
    allowances: dict[tuple[str, str, str], Decimal] = field(default_factory=dict)
    existing_positions: list[dict[str, Any]] = field(default_factory=list)
    # Spec §13 Row 17 — optional JitMonitor handle. When None, the
    # check_jit_adjacency detector returns None silently (fail-soft).
    # Type is `Any` to avoid pulling in src.shield.jit_monitor at module
    # import time — the detector branch lazy-imports the type.
    jit_monitor: Any = None
    # Spec §13 Row 17 — per-LP-step pool overrides. Adapters that resolve
    # the target pool address can stash it on `step.transaction.lp_pool_addr`
    # or `step.receipt["lp_pool_addr"]`; this dict is a runtime escape
    # hatch keyed by step_id for composed plans where the pool is known
    # at preflight time but the transaction isn't yet built.
    lp_pool_addrs: dict[str, str] = field(default_factory=dict)

    def balance_of(self, chain: str, asset: str) -> Decimal:
        return self.balances.get((chain.lower(), asset.upper()), Decimal(0))

    def gas_balance(self, chain: str) -> Decimal:
        return self.native_gas.get(chain.lower(), Decimal(0))

    def allowance_for(self, chain: str, asset: str, spender: str) -> Decimal:
        return self.allowances.get((chain.lower(), asset.upper(), spender.lower()), Decimal(0))


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


def _wallet_for_chain(chain_kind: str, inventory: WalletInventory) -> str | None:
    if chain_kind == "solana":
        return inventory.solana_address
    return inventory.evm_address


def _chain_kind(chain: str) -> str:
    return "solana" if chain.lower() in {"solana", "sol"} else "evm"


def evaluate_preflight(
    *,
    steps: Iterable[ExecutionStepV3],
    inventory: WalletInventory,
    min_native_gas: dict[str, float] | None = None,
) -> list[ExecutionBlocker]:
    """Inspect each step against wallet inventory and return blockers.

    Blockers are the only place execution_plan_v3 says "do not sign yet". A
    step that gets a blocker here will be marked `blocked` by the plan.
    """
    blockers: list[ExecutionBlocker] = []
    min_native_gas = min_native_gas or {"ethereum": 0.005, "base": 0.001, "arbitrum": 0.001, "optimism": 0.001, "polygon": 1.0, "bsc": 0.005, "solana": 0.01}
    seen_codes: set[str] = set()

    for step in steps:
        kind = _chain_kind(step.chain)
        wallet_address = _wallet_for_chain(kind, inventory)
        step_chain = step.chain.lower()

        if wallet_address is None:
            code = f"missing_{kind}_wallet"
            if code not in seen_codes:
                blockers.append(ExecutionBlocker(
                    code=code,
                    severity="blocker",
                    title=f"Connect a {kind.upper()} wallet",
                    detail=(
                        f"Step {step.index} ({step.title}) requires a {kind} wallet but none is connected."
                    ),
                    affected_step_ids=[step.step_id],
                    cta=("Connect Phantom for Solana." if kind == "solana" else "Connect MetaMask or another EVM wallet."),
                ))
                seen_codes.add(code)
            continue

        if step.action in {"approve", "swap", "supply", "stake", "deposit_lp", "bridge", "withdraw"}:
            if step.asset_in and step.amount_in:
                amount = _to_decimal(step.amount_in)
                balance = inventory.balance_of(step_chain, step.asset_in)
                if amount > 0 and balance < amount:
                    blockers.append(ExecutionBlocker(
                        code="insufficient_balance",
                        severity="blocker",
                        title=f"Insufficient {step.asset_in} on {step.chain}",
                        detail=(
                            f"Step {step.index} needs {amount} {step.asset_in} on {step.chain}; "
                            f"wallet currently holds {balance}. Top up before signing."
                        ),
                        affected_step_ids=[step.step_id],
                        cta=f"Bridge or swap into {step.asset_in} on {step.chain} before retrying.",
                    ))

        if step.action != "wait_receipt" and step.action != "verify_balance":
            min_required = Decimal(str(min_native_gas.get(step_chain, 0.0)))
            if min_required > 0:
                gas_balance = inventory.gas_balance(step_chain)
                if gas_balance < min_required:
                    blockers.append(ExecutionBlocker(
                        code="insufficient_gas",
                        severity="blocker",
                        title=f"Insufficient native gas on {step.chain}",
                        detail=(
                            f"Step {step.index} requires roughly {min_required} native gas on {step.chain}; "
                            f"wallet has {gas_balance}."
                        ),
                        affected_step_ids=[step.step_id],
                        cta=f"Send some native {step.chain} gas to the connected wallet.",
                    ))

        if step.action in {"swap", "supply", "stake", "deposit_lp"} and step.asset_in and step.amount_in:
            spender = step.transaction.spender if step.transaction and step.transaction.spender else None
            if spender:
                allowance = inventory.allowance_for(step_chain, step.asset_in, spender)
                amount = _to_decimal(step.amount_in)
                if allowance < amount:
                    # Allowance shortfall is only a blocker when the prior
                    # approve step is not part of the plan.
                    has_approve = any(
                        prior.action == "approve" and prior.asset_in == step.asset_in
                        for prior in steps
                        if prior.index < step.index
                    )
                    if not has_approve:
                        blockers.append(ExecutionBlocker(
                            code="missing_allowance",
                            severity="blocker",
                            title=f"Missing approval for {step.asset_in}",
                            detail=(
                                f"Step {step.index} needs allowance >= {amount} for spender {spender} but current allowance is {allowance}."
                            ),
                            affected_step_ids=[step.step_id],
                            cta="Add an explicit approve step to the plan or grant allowance manually.",
                        ))

    # Spec §13 Row 26 — SELF_TRADE_AGAINST_OWN_LP. Only fires when the user
    # has at least one open V3-family LP NFT on this chain AND a swap step
    # targets a pool address that overlaps with the user's open-LP pool set.
    # We honor two opt-in shapes:
    #   1. The step.transaction has a `.swap_pool_addr` attr (set by
    #      adapters that resolved the pool via getPool), or
    #   2. The step.receipt dict carries `swap_pool_addr` (sidecar/runtime
    #      injection path used by composed plans before sim).
    # Detection short-circuits when the wallet has no positions to keep the
    # hot path free of getPool RPC calls. The blocker is keyed by code so
    # we only attach one even if multiple swap steps overlap.
    try:
        _self_trade_blockers = _check_self_trade(steps, inventory)
        for b in _self_trade_blockers:
            if b.code not in seen_codes:
                blockers.append(b)
                seen_codes.add(b.code)
    except Exception as exc:  # never let a §13 detector crash preflight
        logger.debug("self-trade detector raised: %s", exc)

    # Spec §13 Row 17 — JIT_ATTACK_ADJACENCY. Only runs on EVM LP add/
    # increase steps when a JitMonitor instance is attached to inventory
    # via the `_jit_monitor` sidecar attribute. Sibling to the self-trade
    # block above: fail-soft — if the monitor is None / not started,
    # nothing fires.
    try:
        _jit_blockers = _check_jit_adjacency_blockers(steps, inventory)
        for b in _jit_blockers:
            if b.code not in seen_codes:
                blockers.append(b)
                seen_codes.add(b.code)
    except Exception as exc:  # never let a §13 detector crash preflight
        logger.debug("jit-adjacency detector raised: %s", exc)

    return blockers


def _check_self_trade(
    steps: Iterable[ExecutionStepV3],
    inventory: WalletInventory,
) -> list[ExecutionBlocker]:
    """Run the §13 Row 26 self-trade detector against any swap steps in the
    plan. No-op when the wallet has no recorded open positions.
    """
    if not inventory.existing_positions or not inventory.evm_address:
        return []
    # Only fire when at least one swap step targets a pool we can identify.
    swap_steps = [s for s in steps if s.action == "swap"]
    if not swap_steps:
        return []

    # Pre-resolve the wallet's V3 open-LP pool addresses once. We honor a
    # pre-resolved `pool_address` on each row first (sync path), and fall
    # back to the async detect_self_trade() helper when only token0/token1
    # /fee_bps are present (it will call factory.getPool).
    from src.shield.self_trade import (
        _is_v3_position,
        _norm_addr,
        detect_self_trade,
        detect_self_trade_sync,
    )

    pre_resolved: set[str] = set()
    needs_rpc = False
    for pos in inventory.existing_positions:
        if not _is_v3_position(pos):
            continue
        pre = _norm_addr(pos.get("pool_address") or (pos.get("metadata") or {}).get("pool_address"))
        if pre:
            pre_resolved.add(pre)
        else:
            needs_rpc = True

    out: list[ExecutionBlocker] = []
    blocked_step_ids: list[str] = []

    # Sync fast path — covers the case where inventory already cached
    # the resolved pool address (most common when build_yield_execution_plan
    # injects positions from the position_store).
    if pre_resolved:
        for step in swap_steps:
            pool = _extract_step_pool(step)
            if not pool:
                continue
            code = detect_self_trade_sync(
                inventory.evm_address,
                pool,
                inventory.chain_id or 0,
                owned_pool_addrs=pre_resolved,
            )
            if code:
                blocked_step_ids.append(step.step_id)

    # Async fallback — only run when positions exist that need getPool
    # resolution. Wrap in asyncio.run only when we're outside an event loop;
    # otherwise schedule on the running loop via a thread-safe future.
    if needs_rpc and not blocked_step_ids:
        for step in swap_steps:
            pool = _extract_step_pool(step)
            if not pool:
                continue
            try:
                code = _run_async(
                    detect_self_trade(
                        inventory.evm_address,
                        pool,
                        inventory.chain_id or 0,
                        find_user_positions=_inventory_position_source(inventory),
                    )
                )
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("self_trade async resolve failed: %s", exc)
                continue
            if code:
                blocked_step_ids.append(step.step_id)

    if blocked_step_ids:
        out.append(ExecutionBlocker(
            code="SELF_TRADE_AGAINST_OWN_LP",
            severity="blocker",
            title="Swap would route through your own LP",
            detail=(
                "One of the swap legs in this plan targets a pool you "
                "currently provide liquidity to. Signing would sandwich "
                "your own position. Re-route around the conflicting pool "
                "(different fee tier or aggregator) before broadcasting."
            ),
            affected_step_ids=blocked_step_ids,
            cta="Pick a different fee tier or pool, then re-quote.",
        ))
    return out


def _check_jit_adjacency_blockers(
    steps: Iterable[ExecutionStepV3],
    inventory: WalletInventory,
) -> list[ExecutionBlocker]:
    """Run the §13 Row 17 JIT-attack adjacency detector against any LP
    add/increase steps on EVM chains in the plan.

    Fail-soft: if no JitMonitor is attached, or it hasn't started, this
    returns an empty list — never a false positive.
    """
    monitor = inventory.jit_monitor
    if monitor is None:
        return []
    # Lazy import to avoid pulling shield.jit_monitor into the preflight
    # import graph for callers that don't need it.
    try:
        from src.shield.jit_monitor import (
            JIT_BLOCKER_CODE,
            check_jit_adjacency_sync,
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("jit_monitor import failed: %s", exc)
        return []

    # Only LP add/increase actions on EVM chains are eligible. Solana JIT
    # adjacency is handled by the Solana-specific preflight (V7-007).
    lp_actions = {"deposit_lp", "add_liquidity", "provide_liquidity", "increase_liquidity"}
    lp_steps = [
        s for s in steps
        if (s.action or "").lower() in lp_actions and _chain_kind(s.chain) == "evm"
    ]
    if not lp_steps:
        return []

    blocked_step_ids: list[str] = []
    for step in lp_steps:
        pool = _extract_lp_step_pool(step, inventory)
        if not pool:
            continue
        code = check_jit_adjacency_sync(pool, monitor=monitor)
        if code:
            blocked_step_ids.append(step.step_id)

    if not blocked_step_ids:
        return []

    return [ExecutionBlocker(
        code=JIT_BLOCKER_CODE,
        severity="blocker",
        title="JIT attack adjacency detected",
        detail=(
            "A pending mempool swap above the $100k threshold is queued "
            "against the same pool you're about to add liquidity to. "
            "Signing now risks being sandwiched by a JIT-liquidity "
            "searcher. Shield is requesting a 1-block delay and "
            "re-simulation; retry once the adjacent swap has landed."
        ),
        affected_step_ids=blocked_step_ids,
        cta="Wait 1 block and re-quote, or pick a different fee tier.",
    )]


def _extract_lp_step_pool(
    step: ExecutionStepV3,
    inventory: WalletInventory,
) -> str | None:
    """Pull the LP target pool address. Honors (in order):
      1. inventory.lp_pool_addrs[step_id] — explicit caller override
      2. step.transaction.lp_pool_addr — adapter-stamped
      3. step.transaction.swap_pool_addr — fallback for adapters that
         only stamp the canonical pool key
      4. step.receipt["lp_pool_addr" | "pool_address"] — sidecar/runtime
    """
    override = inventory.lp_pool_addrs.get(step.step_id)
    if override:
        return str(override)
    tx = step.transaction
    if tx is not None:
        for attr in ("lp_pool_addr", "swap_pool_addr", "pool_address"):
            pool = getattr(tx, attr, None)
            if pool:
                return str(pool)
    if step.receipt and isinstance(step.receipt, dict):
        for key in ("lp_pool_addr", "pool_address", "swap_pool_addr"):
            pool = step.receipt.get(key)
            if pool:
                return str(pool)
    return None


def _extract_step_pool(step: ExecutionStepV3) -> str | None:
    """Pull the swap-leg target pool address from whichever metadata
    surface the adapter populated. Returns None when no pool is hinted —
    the detector silently skips such steps."""
    # Adapters built on the V3 router family typically stash the resolved
    # pool on transaction (custom attribute) or receipt (sidecar path).
    tx = step.transaction
    if tx is not None:
        # UnsignedStepTransaction is a dataclass with __slots__-free attrs;
        # an adapter may have monkey-patched a `swap_pool_addr` attribute.
        pool = getattr(tx, "swap_pool_addr", None)
        if pool:
            return str(pool)
    if step.receipt and isinstance(step.receipt, dict):
        pool = step.receipt.get("swap_pool_addr")
        if pool:
            return str(pool)
    return None


def _inventory_position_source(inventory: WalletInventory):
    """Wrap inventory.existing_positions as the async find_user_positions
    callable detect_self_trade() expects. Keeps the async path RPC-free
    when the caller already supplied the position rows."""
    rows = list(inventory.existing_positions)

    async def _fetch(_wallet: str, _chain_id: int) -> list[dict[str, Any]]:
        return rows
    return _fetch


def _run_async(coro):
    """Run an async coroutine from sync context. When called from inside
    an active loop (rare here — preflight is sync-only today), we punt
    via run_until_complete on a fresh loop. Otherwise asyncio.run."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule on a private loop to avoid nested-loop errors.
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
    except RuntimeError:
        pass
    return asyncio.run(coro)
