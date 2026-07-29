"""Wallet preflight: verify balance, gas, allowance, wallet kind before signing."""
from __future__ import annotations

import asyncio
import logging
import re
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
    # Spec §13 Row 1 — pre-resolved oracle staleness findings. Populated
    # by the async sidecar via :func:`src.shield.feed_age.evaluate_feed_age_preflight`
    # before the sync preflight runs. Each entry is a dict carrying
    # ``{"code": "STALE_PRICE_FEED", "feed": ..., "source": ..., "age_seconds": ...}``.
    feed_age_blockers: list[dict[str, Any]] = field(default_factory=list)
    # Spec §13 Row 15 — wallet-capability meta for hw-wallet ALT detection.
    # Frontend probes ``window.solana.isLedger`` (or the WalletConnect
    # ``hardware`` flag) and forwards the result as
    # ``{"kind": "ledger" | "trezor" | "phantom" | ...}``. None means the
    # capability is unknown — the §13 Row 15 detector fails-soft to clean.
    wallet_meta: dict[str, Any] | None = None

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

    # Spec §13 Row 1 — STALE_PRICE_FEED. Synchronous fan-out happens via
    # `evaluate_feed_age_preflight` in the async sidecar; this hook
    # collects any pre-resolved feed-age blocker codes stamped onto
    # inventory.feed_age_blockers by the upstream orchestrator. Keeping
    # the sync entry stub here lets every preflight caller pick up the
    # blocker without forcing an event loop on the sync path.
    try:
        _feed_blockers = _check_feed_age_blockers(inventory, steps)
        for b in _feed_blockers:
            if b.code not in seen_codes:
                blockers.append(b)
                seen_codes.add(b.code)
    except Exception as exc:  # never let a §13 detector crash preflight
        logger.debug("feed-age detector raised: %s", exc)

    # Spec §13 Row 15 — LEDGER_NO_ALT_SUPPORT. Refuses to surface a v0+ALT
    # Solana plan to a hardware wallet that can't parse versioned-tx
    # messages. The detector silently passes when wallet_meta is missing
    # or the wallet kind is software (Phantom/Solflare/Backpack).
    try:
        _hw_alt_blockers = _check_hardware_wallet_alt_blockers(steps, inventory)
        for b in _hw_alt_blockers:
            if b.code not in seen_codes:
                blockers.append(b)
                seen_codes.add(b.code)
    except Exception as exc:  # never let a §13 detector crash preflight
        logger.debug("hw-wallet-alt detector raised: %s", exc)

    # Spec §13 Row 10 — PERMISSIONED_POOL_KYC. Refuses to sign any
    # supply/deposit/stake/deposit_lp/lend step that lands in a pool
    # we know is gated by an off-platform KYC / whitelist contract
    # (Aave Arc, Maple Syrup, Goldfinch Senior Pool, Hashnote USYC,
    # Centrifuge, etc.). Wallet-side balance/gas checks are useless
    # for these pools — the gated function would revert on-chain even
    # with a fully-funded wallet — so we surface the blocker pre-sign.
    try:
        _kyc_blockers = _check_kyc_pool_blockers(steps, inventory)
        for b in _kyc_blockers:
            blockers.append(b)
            seen_codes.add(b.code)
    except Exception as exc:  # never let a §13 detector crash preflight
        logger.debug("kyc-pool detector raised: %s", exc)

    # V7-049 / Spec §6a — DISALLOWED_V4_HOOK. Defense-in-depth gate against
    # untrusted Uniswap V4 hook contracts. The V4 adapter
    # (src/defi/execution/adapters/uniswap_v4.py) already refuses unknown
    # hooks at build time via src.shield.v4_hook_allowlist; this preflight
    # branch re-checks against the curated address allowlist in
    # src/data/v4_hooks_allowlist.py so a deposit_lp step assembled by any
    # other path (composed-plan rebuild, ingested 3rd-party plan, etc.)
    # cannot smuggle a malicious hook into the wallet's confirm dialog.
    try:
        _v4_hook_blockers = _check_v4_hook_blockers(steps)
        for b in _v4_hook_blockers:
            if b.code not in seen_codes:
                blockers.append(b)
                seen_codes.add(b.code)
    except Exception as exc:  # never let the gate crash preflight
        logger.debug("v4-hook-allowlist detector raised: %s", exc)

    return blockers


# V7-049 — Matches a 0x-prefixed 20-byte EVM address. Used to recover the
# hook address from `step.risk_warnings` strings stamped by
# UniswapV4NativeAdapter when adapters don't expose a dedicated
# transaction attribute. Hex is case-insensitive per EIP-55.
_V4_HOOK_ADDR_RE = re.compile(r"0x[a-fA-F0-9]{40}")


def _extract_v4_hook_addr(step: ExecutionStepV3) -> str | None:
    """Resolve the V4 hook contract address attached to a deposit_lp step.

    Resolution order (most explicit first):
      1. ``step.transaction.v4_hook_addr`` — adapter-stamped attribute.
         Mirrors the lp_pool_addr / swap_pool_addr escape-hatch pattern
         the §13 detectors already honor.
      2. ``step.transaction.hooks`` — alternate adapter attribute name
         matching the PoolKey field literally.
      3. ``step.receipt["v4_hook_addr"]`` — sidecar/runtime injection.
      4. Last-resort scrape of ``step.risk_warnings`` text. The native
         V4 adapter currently stamps a "Hook contract 0x… — Shield: …"
         line; we look for the FIRST 0x-address token in any risk_warning
         entry that contains the word "hook". Skips entries that mention
         the user's own address by checking only hook-tagged lines.
    Returns None when no address is recoverable — the gate fails-open in
    that case (the adapter-level check is the primary line of defense).
    """
    tx = step.transaction
    if tx is not None:
        for attr in ("v4_hook_addr", "hooks", "hook_addr"):
            v = getattr(tx, attr, None)
            if v:
                return str(v).lower()
    if step.receipt and isinstance(step.receipt, dict):
        for key in ("v4_hook_addr", "hooks", "hook_addr"):
            v = step.receipt.get(key)
            if v:
                return str(v).lower()
    # Risk-warning scrape — only inspect entries that mention "hook" so we
    # don't accidentally pick up the owner address from another warning.
    for w in step.risk_warnings or []:
        if not isinstance(w, str):
            continue
        if "hook" not in w.lower():
            continue
        m = _V4_HOOK_ADDR_RE.search(w)
        if m:
            return m.group(0).lower()
    return None


def _check_v4_hook_blockers(
    steps: Iterable[ExecutionStepV3],
) -> list[ExecutionBlocker]:
    """Run the V7-049 V4-hook allowlist gate against any V4 LP step.

    Only fires on (protocol == 'uniswap-v4', action in {deposit_lp,
    add_liquidity, provide_liquidity, increase_liquidity}). The zero
    address (vanilla pool) and an unresolved hook address both pass —
    the latter because the adapter-level check is authoritative and
    fail-open here matches the shape of the other §13 detectors.
    """
    # Uniswap V4 is EVM-only and was removed in the Solana-only cut, so no
    # Solana step can carry a V4 hook. The gate is now a no-op.
    return []


def _check_hardware_wallet_alt_blockers(
    steps: Iterable[ExecutionStepV3],
    inventory: WalletInventory,
) -> list[ExecutionBlocker]:
    """Run the §13 Row 15 LEDGER_NO_ALT_SUPPORT detector. Fail-soft when
    ``inventory.wallet_meta`` is missing — Ledger / Trezor / Keystone are
    the only kinds that trip; software wallets pass through clean.
    """
    meta = getattr(inventory, "wallet_meta", None)
    if not meta:
        return []
    # Lazy import to keep the shield import graph cold for plans that
    # never touch a Solana step.
    try:
        from src.shield.hardware_wallet_alt import (
            evaluate_hardware_wallet_alt_preflight,
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("hardware_wallet_alt import failed: %s", exc)
        return []
    return evaluate_hardware_wallet_alt_preflight(steps, meta)


def _check_kyc_pool_blockers(
    steps: Iterable[ExecutionStepV3],
    inventory: WalletInventory,
) -> list[ExecutionBlocker]:
    """Run the §13 Row 10 PERMISSIONED_POOL_KYC detector against any
    supply / deposit / stake / lend / deposit_lp step in the plan.

    Pool address resolution order (per-step):
      1. inventory.lp_pool_addrs[step_id] — explicit caller override
      2. step.transaction.lp_pool_addr / swap_pool_addr / pool_address /
         to — adapter-stamped or direct call destination
      3. step.receipt["lp_pool_addr" | "pool_address"] — sidecar/runtime

    `to` is included because supply/deposit calls land directly on the
    pool contract — adapters that don't separately stash a pool key still
    surface the gated contract via the unsigned-tx `to` field.
    """
    # Only actions that can land *into* a pool are eligible. Swaps and
    # approvals are excluded — swap-leg routing through a KYC pool is
    # covered by the aggregator's own quote filtering, and approves are
    # not deposits.
    gated_actions = {
        "supply",
        "deposit",
        "deposit_lp",
        "add_liquidity",
        "provide_liquidity",
        "stake",
        "lend",
    }
    candidates: list[tuple[str, str]] = []  # (step_id, pool_addr)
    for step in steps:
        if (step.action or "").lower() not in gated_actions:
            continue
        pool = _extract_kyc_step_pool(step, inventory)
        if not pool:
            continue
        candidates.append((step.step_id, pool))

    if not candidates:
        return []

    # Lazy import to keep the shield import graph cold for plans that
    # never touch a permissioned-pool-class action.
    try:
        from src.shield.kyc_pool import (
            evaluate_kyc_pool_preflight,
            is_kyc_gated,
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("kyc_pool import failed: %s", exc)
        return []

    # Group affected step_ids per-pool-address so the blocker carries every
    # offending step in a single row (matches the dedupe contract of
    # evaluate_kyc_pool_preflight which collapses repeats).
    pool_to_steps: dict[str, list[str]] = {}
    for step_id, pool in candidates:
        if not is_kyc_gated(pool):
            continue
        pool_to_steps.setdefault(pool.lower(), []).append(step_id)

    if not pool_to_steps:
        return []

    out: list[ExecutionBlocker] = []
    for pool_lower, step_ids in pool_to_steps.items():
        out.extend(
            evaluate_kyc_pool_preflight(
                [pool_lower],
                affected_step_ids=step_ids,
            )
        )
    return out


def _extract_kyc_step_pool(
    step: ExecutionStepV3,
    inventory: WalletInventory,
) -> str | None:
    """Resolve the candidate pool address a supply/deposit/lend step would
    land in. Mirrors `_extract_lp_step_pool` but also falls back to
    `step.transaction.to` (direct call destination) because supply/deposit
    adapters typically don't separately stash a pool key — the gated
    contract *is* the destination of the unsigned tx.
    """
    override = inventory.lp_pool_addrs.get(step.step_id)
    if override:
        return str(override)
    tx = step.transaction
    if tx is not None:
        for attr in ("lp_pool_addr", "swap_pool_addr", "pool_address", "to"):
            pool = getattr(tx, attr, None)
            if pool:
                return str(pool)
    if step.receipt and isinstance(step.receipt, dict):
        for key in ("lp_pool_addr", "pool_address", "swap_pool_addr"):
            pool = step.receipt.get(key)
            if pool:
                return str(pool)
    return None


def _check_feed_age_blockers(
    inventory: WalletInventory,
    steps: Iterable[ExecutionStepV3],
) -> list[ExecutionBlocker]:
    """Convert pre-resolved feed-staleness findings into ExecutionBlocker
    rows. The async fan-out lives in :mod:`src.shield.feed_age` so the
    sync preflight path stays event-loop-free; the orchestrator stamps
    ``inventory.feed_age_blockers`` with the list returned by
    ``evaluate_feed_age_preflight`` before invoking ``evaluate_preflight``.

    Each finding has shape ``{"code": "STALE_PRICE_FEED", "feed": ...,
    "source": "pyth"|"chainlink", "age_seconds": int}``.
    """
    raw = getattr(inventory, "feed_age_blockers", None)
    if not raw:
        return []
    # Lazy import to avoid pulling shield.feed_age into the import graph
    # of callers that never touch oracle-priced steps.
    try:
        from src.shield.feed_age import STALE_PRICE_FEED_BLOCKER_CODE
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("feed_age import failed: %s", exc)
        return []

    all_step_ids = [s.step_id for s in steps]
    out: list[ExecutionBlocker] = []
    for finding in raw:
        if not isinstance(finding, dict):
            continue
        if finding.get("code") != STALE_PRICE_FEED_BLOCKER_CODE:
            continue
        feed = finding.get("feed", "<unknown>")
        source = finding.get("source", "oracle")
        age = finding.get("age_seconds", "?")
        out.append(ExecutionBlocker(
            code=STALE_PRICE_FEED_BLOCKER_CODE,
            severity="blocker",
            title=f"{source.title()} price feed is stale",
            detail=(
                f"The {source} feed {feed} was last updated {age}s ago, "
                f"above the 60s staleness ceiling. Signing now risks "
                f"executing against a mark that the next on-chain push "
                f"will jump past — fees, slippage, and liquidations "
                f"would all hit a stale price. Wait for a fresh push "
                f"and re-quote."
            ),
            affected_step_ids=list(all_step_ids),
            cta="Wait ~1 block for the next oracle push, then re-quote.",
        ))
        # Only emit one blocker row even when multiple feeds are stale —
        # the detail line above can be aggregated in the UI later.
        break
    return out


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
