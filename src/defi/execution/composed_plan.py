"""Spec §6c — cross-chain composed plans (snapshot → block → rebuild → promote).

A composed plan is a multi-leg LP intent that crosses chains or has an
async dependency. The chat surface shows all legs upfront in a single
thread; the destination-side step blocks on `pending_dst_fill` until
the bridge solver fills, then the runtime rebuilds the deposit step
with the actual delta and promotes it to ready.

This module ships the four primitives:

  - snapshot(quote, expected_dst_amount, slippage_band_bps) — capture
    the solver-quoted destination amount at plan-build time.
  - block(plan_step, blocker_code) — mark a step as blocked on an
    async fill (PENDING_DST_FILL, PENDING_EPOCH_ENTRY, etc.).
  - rebuild(plan_step, actual_dst_amount) — re-emit the dependent
    step's calldata with the actual delta after fill resolution.
  - promote(plan_step) — flip a step from blocked → ready once
    rebuild succeeds.

Bridge fill detection lives in DeBridgeOrderWatcher (webhook + RPC
poll dual-signal). The composed-plan builder is bridge-agnostic — pass
any Bridge implementation that satisfies the protocol.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from src.defi.execution.models import ExecutionStepV3

logger = logging.getLogger(__name__)


class Bridge(Protocol):
    """Bridge interface — deBridge DLN, LI.FI, Socket all conform."""

    name: str

    async def quote(
        self,
        *,
        src_chain_id: int,
        dst_chain_id: int,
        token_in: str,
        token_out: str,
        amount: int,
        recipient: str,
    ) -> dict[str, Any]:
        """Return {expected_dst_amount, slippage_bps_band, quote_id, ttl_s}."""
        ...

    async def status(self, order_id: str) -> dict[str, Any]:
        """Return {state: 'created'|'filled'|'cancelled'|'failed', actual_dst_amount?}."""
        ...


@dataclass
class Snapshot:
    """Captured solver quote at plan-build time."""

    bridge_name: str
    src_chain_id: int
    dst_chain_id: int
    token_in: str
    token_out: str
    src_amount: int
    expected_dst_amount: int
    slippage_bps_band_min: int
    slippage_bps_band_max: int
    quote_id: str | None = None
    captured_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "bridge_name": self.bridge_name,
            "src_chain_id": self.src_chain_id,
            "dst_chain_id": self.dst_chain_id,
            "token_in": self.token_in,
            "token_out": self.token_out,
            "src_amount": str(self.src_amount),
            "expected_dst_amount": str(self.expected_dst_amount),
            "slippage_bps_band": {
                "min": self.slippage_bps_band_min,
                "max": self.slippage_bps_band_max,
            },
            "quote_id": self.quote_id,
            "captured_at": self.captured_at,
        }


@dataclass
class FillResolution:
    """Actual fill data observed after webhook / RPC poll resolves."""

    order_id: str
    state: str                       # "filled" | "cancelled" | "failed" | "timeout"
    actual_dst_amount: int | None = None
    realized_slippage_bps: int | None = None
    resolved_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "state": self.state,
            "actual_dst_amount": (
                str(self.actual_dst_amount) if self.actual_dst_amount is not None else None
            ),
            "realized_slippage_bps": self.realized_slippage_bps,
            "resolved_at": self.resolved_at,
        }


async def snapshot_bridge_quote(
    bridge: Bridge,
    *,
    src_chain_id: int,
    dst_chain_id: int,
    token_in: str,
    token_out: str,
    amount: int,
    recipient: str,
    slippage_band_min_bps: int = 5,
    slippage_band_max_bps: int = 20,
) -> Snapshot:
    """Step 1 of §6c — capture the bridge's expected destination amount."""
    import time

    q = await bridge.quote(
        src_chain_id=src_chain_id,
        dst_chain_id=dst_chain_id,
        token_in=token_in,
        token_out=token_out,
        amount=amount,
        recipient=recipient,
    )
    expected_dst = int(q.get("expected_dst_amount", 0))
    if expected_dst <= 0:
        raise ValueError(f"Bridge {bridge.name} returned zero/missing expected_dst_amount.")
    return Snapshot(
        bridge_name=bridge.name,
        src_chain_id=src_chain_id,
        dst_chain_id=dst_chain_id,
        token_in=token_in,
        token_out=token_out,
        src_amount=amount,
        expected_dst_amount=expected_dst,
        slippage_bps_band_min=int(q.get("slippage_bps_band", {}).get("min", slippage_band_min_bps)),
        slippage_bps_band_max=int(q.get("slippage_bps_band", {}).get("max", slippage_band_max_bps)),
        quote_id=q.get("quote_id"),
        captured_at=time.time(),
    )


def block_step_for_async_fill(step: ExecutionStepV3, *, blocker_code: str = "PENDING_DST_FILL") -> None:
    """Step 2 — mark the deposit step blocked on an async fill.

    Mutates the step in place; idempotent.
    """
    if blocker_code not in step.blocker_codes:
        step.blocker_codes.append(blocker_code)
    step.status = "blocked"


async def watch_for_fill(
    bridge: Bridge,
    order_id: str,
    *,
    poll_interval_s: float = 2.0,
    max_poll_s: float = 900.0,  # 15 minutes
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
) -> FillResolution:
    """Step 3 — exponential-backoff poll for the bridge order to fill.

    Webhook integration is the preferred signal in production; this RPC
    poller is the always-on fallback.
    """
    import time

    started = time.time()
    interval = poll_interval_s
    while True:
        elapsed = time.time() - started
        if elapsed > max_poll_s:
            return FillResolution(
                order_id=order_id,
                state="timeout",
                resolved_at=time.time(),
            )
        try:
            status = await bridge.status(order_id)
        except Exception as exc:  # noqa: BLE001 — defensive
            logger.warning("Bridge status poll failed: %s", exc)
            status = {"state": "unknown"}
        state = status.get("state", "unknown")
        if on_progress:
            try:
                await on_progress({"state": state, "elapsed_s": elapsed})
            except Exception:  # noqa: BLE001
                pass
        if state in {"filled", "cancelled", "failed"}:
            actual = status.get("actual_dst_amount")
            realized = status.get("realized_slippage_bps")
            return FillResolution(
                order_id=order_id,
                state=state,
                actual_dst_amount=int(actual) if actual is not None else None,
                realized_slippage_bps=int(realized) if realized is not None else None,
                resolved_at=time.time(),
            )
        await asyncio.sleep(interval)
        # Backoff up to 15 seconds.
        interval = min(interval * 1.5, 15.0)


def rebuild_step_with_actual_delta(
    step: ExecutionStepV3,
    *,
    snapshot: Snapshot,
    fill: FillResolution,
    rebuilder: Callable[[int], ExecutionStepV3] | None = None,
) -> ExecutionStepV3:
    """Step 4 — rebuild the dependent step with the actual fill amount.

    When `rebuilder` is provided, it gets called with the actual dst
    amount and must return a fresh ExecutionStepV3 with updated
    calldata + amount_in. The fresh step inherits the original
    step_id, depends_on, and index so dependents stay coherent.

    Without a `rebuilder`, this fn just updates `step.fill_resolved`
    and clears the PENDING_DST_FILL blocker. The actual calldata
    refresh is the caller's responsibility.
    """
    step.snapshot = snapshot.to_dict()
    step.fill_resolved = fill.to_dict()
    if fill.state != "filled":
        # Refund / cancellation surfaces a recovery hook.
        from src.defi.recovery import FailureKind, decide_recovery

        recovery = decide_recovery(
            FailureKind.BRIDGE_SUBMISSION_FAILED
            if fill.state in {"cancelled", "failed"}
            else FailureKind.UNKNOWN,
            step_kind="bridge",
            elapsed_since_fail_s=0,
        )
        step.recovery_hook = recovery.to_dict()
        return step
    # Clear the blocker code and re-emit calldata via rebuilder.
    step.blocker_codes = [c for c in step.blocker_codes if c != "PENDING_DST_FILL"]
    if rebuilder and fill.actual_dst_amount is not None:
        try:
            fresh = rebuilder(fill.actual_dst_amount)
            # Copy over identity so dependents don't break.
            fresh.step_id = step.step_id
            fresh.index = step.index
            fresh.depends_on = step.depends_on
            return fresh
        except Exception as exc:  # noqa: BLE001
            logger.exception("rebuilder failed: %s", exc)
    return step


def promote_step_to_ready(step: ExecutionStepV3) -> None:
    """Step 4b — flip a freshly-rebuilt step from blocked → ready.

    Asserts the blocker is cleared and fill is resolved before
    flipping. Caller must call this AFTER rebuild_step_with_actual_delta
    confirmed `fill.state == "filled"`.
    """
    if step.blocker_codes:
        raise ValueError(
            f"Cannot promote step with active blocker_codes: {step.blocker_codes}"
        )
    if not step.fill_resolved or step.fill_resolved.get("state") != "filled":
        raise ValueError("Cannot promote — fill not resolved.")
    step.status = "ready"


# ── RC7a — composed-plan signability invariant ──
#
# Hard invariant: every non-blocked step in a composed plan MUST carry an
# unsigned-tx payload (`step.transaction is not None`) before the plan is
# emitted to the user. Pass A H04/H05/H06 leaked composed-plan cards where
# the deBridge bridge step had `transaction: null` while still reading as
# `status: "ready"` — if the user clicked Sign, the wallet would either
# noop or skip ahead to the next step out of order. Both outcomes are
# financial-loss bugs.
#
# Call `assert_signable_composed_plan(plan)` from the composed-plan emitter
# BEFORE returning the card. The function returns a typed
# `ComposedPlanIncompleteTxError` (caught by the emitter and reshaped into
# a `COMPOSED_PLAN_INCOMPLETE_TX` blocker) when any step violates the
# invariant.


class ComposedPlanIncompleteTxError(ValueError):
    """Composed plan has at least one non-blocked step with `transaction is None`.

    Carries the offending step's `index` and `step_id` so the caller can
    convert the exception into a structured `COMPOSED_PLAN_INCOMPLETE_TX`
    blocker. Per spec §6c, refusing the emission is mandatory; emitting
    the card with null calldata is a financial-loss bug.
    """

    def __init__(self, *, step_index: int, step_id: str, action: str) -> None:
        self.step_index = step_index
        self.step_id = step_id
        self.action = action
        super().__init__(
            f"composed_plan step index={step_index} step_id={step_id} action={action} "
            f"has transaction=None and status != 'blocked' — refusing emission."
        )


def assert_signable_composed_plan(plan: Any) -> None:
    """RC7a invariant — refuse emission if any non-blocked step is non-signable.

    A step is signable iff it has `transaction is not None`. A step is
    exempt from the signability check when it is "blocked" — either by
    `status == "blocked"` (set by `block_step_for_async_fill`) OR by
    carrying any `blocker_codes` (the recompute pass can flip
    status back to "pending" if no plan-level blocker links to this
    step, but the step's own blocker_codes list remains authoritative
    for §6c PENDING_DST_FILL semantics).

    Raises `ComposedPlanIncompleteTxError` for the first offending step.
    """
    steps = getattr(plan, "steps", None) or []
    for step in steps:
        status = getattr(step, "status", None)
        if status == "blocked":
            continue
        blocker_codes = getattr(step, "blocker_codes", None) or []
        if blocker_codes:
            # Has at least one step-level blocker (PENDING_DST_FILL,
            # PENDING_EPOCH_ENTRY, etc.); deferred-rebuild semantics
            # mean transaction is allowed to be None until the
            # runtime promotes the step to ready.
            continue
        tx = getattr(step, "transaction", None)
        if tx is None:
            raise ComposedPlanIncompleteTxError(
                step_index=getattr(step, "index", -1),
                step_id=getattr(step, "step_id", "?"),
                action=str(getattr(step, "action", "?")),
            )


# ── RC7b — native-wrap detection ──
#
# Spec §13 row 3 (native ETH V3 LP) mandates wrap-first, never swap.
# Pass A H03 leaked a swap-then-LP plan where the canonical flow is
# wrap(ETH)→LP(WETH). The router was eating wrap fees + slippage on a
# free conversion.
#
# `is_native_wrap_required(step)` returns True for steps where:
#   * asset_in is the native gas token of the chain (ETH, MATIC, BNB,
#     AVAX, SOL — though SOL uses a different mechanism handled by the
#     Solana sidecar; this fn returns True only for EVM natives)
#   * verb is in the wrap-required set (lp_mint, deposit_lp,
#     provide_liquidity, supply when target_pool asset is wrapped)
#
# `build_wrap_step(...)` returns a fully-signable wrap step using
# WETH9.deposit() selector 0xd0e30db0 — verified against on-chain
# WETH9 (0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2 ethereum), and the
# same selector for WMATIC/WBNB/WAVAX (all clone the WETH9 ABI).
#
# Sources (verified):
#   * WETH9 deposit() selector — keccak256("deposit()")[:4] == 0xd0e30db0
#     Reference: ethereum/EIPs etherscan WETH9 0xc02a...756cc2
#   * WMATIC, WBNB, WAVAX, WETH(non-mainnet) all share the WETH9 ABI:
#     - WETH(arbitrum)  0x82af49447d8a07e3bd95bd0d56f35241523fbab1
#     - WETH(optimism)  0x4200000000000000000000000000000000000006
#     - WETH(base)      0x4200000000000000000000000000000000000006
#     - WETH(linea)     0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f
#     - WETH(scroll)    0x5300000000000000000000000000000000000004
#     - WETH(blast)     0x4300000000000000000000000000000000000004
#     - WETH(zksync)    0x5aea5775959fbc2557cc8789bc1bf90a239d9a91
#     - WMATIC(polygon) 0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270
#     - WBNB(bsc)       0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c
#     - WAVAX(avax)     0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7
# All call `deposit() external payable` — msg.value carries the native
# amount, contract mints the wrapped ERC20 1:1 to msg.sender.

# Canonical wrap addresses by chain. Keys are lowercase chain slugs;
# values are the address of the wrapped-native ERC20 on that chain
# (verified against block explorer label).
_WRAPPED_NATIVE_BY_CHAIN: dict[str, tuple[str, str]] = {
    # (wrapped_symbol, contract_address)
    "ethereum":  ("WETH",   "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"),
    "arbitrum":  ("WETH",   "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"),
    "optimism":  ("WETH",   "0x4200000000000000000000000000000000000006"),
    "base":      ("WETH",   "0x4200000000000000000000000000000000000006"),
    "linea":     ("WETH",   "0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f"),
    "scroll":    ("WETH",   "0x5300000000000000000000000000000000000004"),
    "blast":     ("WETH",   "0x4300000000000000000000000000000000000004"),
    "zksync":    ("WETH",   "0x5aea5775959fbc2557cc8789bc1bf90a239d9a91"),
    "polygon":   ("WMATIC", "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270"),
    "bsc":       ("WBNB",   "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"),
    "avalanche": ("WAVAX",  "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7"),
}

# Native gas tokens that NEED wrapping for ERC20 surfaces. SOL is excluded
# here because Solana wraps via SPL `Token::SyncNative` — different
# mechanism, handled by the Solana sidecar.
_NATIVE_GAS_BY_CHAIN: dict[str, str] = {
    "ethereum": "ETH",
    "arbitrum": "ETH",
    "optimism": "ETH",
    "base":     "ETH",
    "linea":    "ETH",
    "scroll":   "ETH",
    "blast":    "ETH",
    "zksync":   "ETH",
    "polygon":  "MATIC",
    "bsc":      "BNB",
    "avalanche": "AVAX",
}

# Verbs that require ERC20-shaped input — native must be wrapped first.
_WRAP_REQUIRED_ACTIONS: frozenset[str] = frozenset({
    "lp_mint", "deposit_lp", "provide_liquidity", "supply", "add_liquidity",
})

# Canonical WETH9-family deposit() selector. keccak256("deposit()")[:4].
WETH9_DEPOSIT_SELECTOR: str = "0xd0e30db0"


def is_native_wrap_required(
    *,
    chain: str,
    asset_in: str,
    action: str,
) -> bool:
    """RC7b — return True when a wrap step must be prepended.

    Args:
      chain:     lowercased chain slug (e.g. "ethereum", "base")
      asset_in:  step's input asset symbol (e.g. "ETH", "MATIC")
      action:    step's verb (e.g. "lp_mint", "supply")
    """
    chain_l = (chain or "").lower()
    asset_u = (asset_in or "").upper()
    act_l = (action or "").lower()
    native = _NATIVE_GAS_BY_CHAIN.get(chain_l)
    if not native:
        return False
    if asset_u != native:
        return False
    if act_l not in _WRAP_REQUIRED_ACTIONS:
        return False
    if chain_l not in _WRAPPED_NATIVE_BY_CHAIN:
        return False
    return True


def get_wrapped_native_for_chain(chain: str) -> tuple[str, str] | None:
    """Return (wrapped_symbol, address) for the chain's canonical wrapped
    native token, or None if the chain isn't EVM-supported here.
    """
    return _WRAPPED_NATIVE_BY_CHAIN.get((chain or "").lower())


# Chain-id map mirrors the broader registry; kept local so callers don't
# need to thread `_CHAIN_ID_MAP` from build_yield_execution_plan.
_WRAP_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1, "arbitrum": 42161, "optimism": 10, "base": 8453,
    "linea": 59144, "scroll": 534352, "blast": 81457, "zksync": 324,
    "polygon": 137, "bsc": 56, "avalanche": 43114,
}


def build_wrap_step(
    *,
    chain: str,
    native_symbol: str,
    amount_wei: int,
    index: int = 1,
) -> ExecutionStepV3:
    """RC7b — emit a signable WETH9.deposit() wrap step.

    `amount_wei` is the integer base-units amount of native gas token to
    wrap (1 ETH = 10**18). The returned step carries the verified WETH9
    deposit() selector `0xd0e30db0` and `value` = amount_wei.

    Raises ValueError when `chain` isn't in the wrapped-native table.
    """
    from src.defi.execution.models import UnsignedStepTransaction, make_step

    chain_l = (chain or "").lower()
    wrap_meta = _WRAPPED_NATIVE_BY_CHAIN.get(chain_l)
    if wrap_meta is None:
        raise ValueError(f"build_wrap_step: chain {chain!r} has no canonical wrapped native.")
    wrapped_sym, wrapped_addr = wrap_meta
    chain_id = _WRAP_CHAIN_IDS.get(chain_l)
    if chain_id is None:
        raise ValueError(f"build_wrap_step: chain {chain!r} has no chain_id mapping.")
    if amount_wei <= 0:
        raise ValueError("build_wrap_step: amount_wei must be > 0.")
    value_hex = "0x" + format(amount_wei, "x")
    return make_step(
        index=index,
        action="approve",  # 'wrap' isn't in canonical StepAction enum; reuse 'approve' flow
        title=f"Wrap {native_symbol} → {wrapped_sym}",
        description=(
            f"WETH9-style deposit() at {wrapped_addr}. msg.value carries the "
            f"native {native_symbol}; the contract mints {wrapped_sym} 1:1 to "
            f"msg.sender. Required because the destination pool/protocol expects "
            f"ERC20 {wrapped_sym}, not native {native_symbol}."
        ),
        chain=chain_l,
        wallet="MetaMask",
        protocol="weth9-wrap",
        asset_in=native_symbol,
        asset_out=wrapped_sym,
        slippage_bps=0,
        gas_estimate_usd=1.4,
        duration_estimate_s=15,
        transaction=UnsignedStepTransaction(
            chain_kind="evm",
            chain_id=chain_id,
            to=wrapped_addr,
            data=WETH9_DEPOSIT_SELECTOR,
            value=value_hex,
            spender=wrapped_addr,
        ),
        risk_warnings=[
            f"Wrap converts native {native_symbol} to {wrapped_sym} 1:1; "
            f"unwrap is symmetric via withdraw(uint256).",
        ],
    )
