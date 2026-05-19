"""ExecutionPlanV3 dataclasses + helpers.

Mirrors `src/api/schemas/agent.py::ExecutionPlanV3Payload` so adapters can
build/serialize plans without importing the Pydantic FastAPI layer."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from uuid import uuid4

StepAction = Literal[
    "approve",
    "swap",
    "bridge",
    "deposit_lp",
    "supply",
    "stake",
    "wait_receipt",
    "verify_balance",
    "claim_rewards",
    "compound_rewards",
    "withdraw",
    # V7-074 — One-click revoke action. Emitted by the nexus_revoke
    # adapter and consumed by the policy-revoke verifier (which calls
    # `assert_session_key_revoked` from src/auth/session_key_mirror.py
    # to mirror-check the on-chain registry before promoting the step).
    "revoke_session_key",
    # Spec §12 canonical step kinds (PDF v1.0 plan schema, page ~36):
    #     kind: enum(APPROVE, PERMIT2_SIG, SWAP, BRIDGE, WRAP_NATIVE,
    #                UNWRAP_NATIVE, ATA_CREATE, TICK_ARRAY_INIT,
    #                BIN_ARRAY_INIT, MINT_POSITION, INCREASE_LIQUIDITY,
    #                DEPOSIT, STAKE, COMPOUND, MULTICALL)
    # The 12 legacy lowercase verbs above already cover APPROVE/SWAP/
    # BRIDGE/STAKE/DEPOSIT(==deposit_lp/supply)/COMPOUND(==compound_rewards).
    # The 9 entries below close the §12 gap. They are additive only —
    # no existing emitter is rewritten this cycle. Adapter wiring for
    # MULTICALL / PERMIT2_SIG / WRAP_NATIVE / UNWRAP_NATIVE / ATA_CREATE /
    # TICK_ARRAY_INIT / BIN_ARRAY_INIT / MINT_POSITION / INCREASE_LIQUIDITY
    # is tracked as a follow-up; right now several adapters reuse `approve`
    # or `withdraw` as placeholders (see composed_plan.py:505 wrap-as-approve
    # and multicall_bundler.py:108 withdraw-as-V3-decreaseLiquidity).
    "PERMIT2_SIG",
    "WRAP_NATIVE",
    "UNWRAP_NATIVE",
    "ATA_CREATE",
    "TICK_ARRAY_INIT",
    "BIN_ARRAY_INIT",
    "MINT_POSITION",
    "INCREASE_LIQUIDITY",
    "MULTICALL",
]

# V7-074 — Public StepAction constants so the rest of the codebase
# can import a single canonical symbol without re-typing string
# literals (the Literal[...] above is the type, not a value namespace).
# Add new constants here when new actions land in the Literal above.
REVOKE_SESSION_KEY = "revoke_session_key"

# Spec §12 canonical-verb constants. Mirrors the upstream enum literally
# so adapters/tests can import a single symbol per verb when wiring lands.
PERMIT2_SIG = "PERMIT2_SIG"
WRAP_NATIVE = "WRAP_NATIVE"
UNWRAP_NATIVE = "UNWRAP_NATIVE"
ATA_CREATE = "ATA_CREATE"
TICK_ARRAY_INIT = "TICK_ARRAY_INIT"
BIN_ARRAY_INIT = "BIN_ARRAY_INIT"
MINT_POSITION = "MINT_POSITION"
INCREASE_LIQUIDITY = "INCREASE_LIQUIDITY"
MULTICALL = "MULTICALL"

# Frozen set of all 15 spec §12 canonical verbs (UPPER_SNAKE form). Tests
# pin this against the StepAction Literal so spec drift is caught.
SPEC_STEP_KINDS: frozenset[str] = frozenset({
    "APPROVE", "PERMIT2_SIG", "SWAP", "BRIDGE", "WRAP_NATIVE", "UNWRAP_NATIVE",
    "ATA_CREATE", "TICK_ARRAY_INIT", "BIN_ARRAY_INIT", "MINT_POSITION",
    "INCREASE_LIQUIDITY", "DEPOSIT", "STAKE", "COMPOUND", "MULTICALL",
})
StepStatus = Literal[
    "blocked", "pending", "queued", "ready", "signing", "submitted", "confirmed", "verified", "failed", "skipped"
]
PlanStatus = Literal[
    # Legacy runtime statuses kept as backward-compat shims.
    "draft", "blocked", "ready", "executing", "complete", "failed", "aborted",
    # Spec §12 canonical vocabulary — runtime is migrating to these. Both
    # spellings coexist while writers convert; the §5 state machine maps
    # legacy → canonical via _PLAN_TO_PIPELINE_STATE.
    "DRAFTING", "READY_TO_SIGN", "SIGNING_IN_PROGRESS", "BROADCASTED",
    "PENDING_DST_FILL", "REBUILDING", "CONFIRMING", "VERIFYING", "INDEXED",
    "FAILED", "STUCK_BALANCE", "CANCELLED",
]
RiskGate = Literal["clear", "soft_warn", "hard_block"]
WalletKind = Literal["MetaMask", "Phantom", "WalletConnect"]


@dataclass
class UnsignedStepTransaction:
    chain_kind: Literal["evm", "solana"]
    chain_id: int | None = None
    to: str | None = None
    data: str | None = None
    value: str | None = None
    gas: str | None = None
    serialized: str | None = None
    spender: str | None = None
    # §13 Row 15 — flag set by Solana adapters when the unsigned tx is a
    # v0 (versioned) message that references one or more Address Lookup
    # Tables. The hardware-wallet preflight check refuses to surface such
    # plans to Ledger/Trezor/Keystone wallets that can't parse v0 messages.
    requires_alt: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# Spec §6c — known step-level blocker codes for composed plans.
# Surface as enum-shaped constants for IDE help; matched as strings.
KNOWN_BLOCKER_CODES: frozenset[str] = frozenset({
    "PENDING_DST_FILL",            # bridge leg in-flight, deposit awaits actual delta
    "ADAPTER_QUOTE_REQUIRED",      # quote expired, must re-fetch before sign
    "PRICE_DRIFT_RESIMULATE",      # >N bps drift since simulation, re-sim needed
    "APPROVAL_MISSING",            # upstream approve not yet broadcast/confirmed
    "ATA_CREATION_MISSING",        # Solana ATA must be created first
    "PENDING_EPOCH_ENTRY",         # Pendle / Curve gauge / Marinade native epoch boundary
    "PENDING_LIDO_QUEUE",          # Lido stake queue wait
    "GAS_TOPUP_REQUIRED",          # dst-chain native gas insufficient
    "PERMISSIONED_POOL_KYC",       # Maple / Goldfinch / Hashnote — KYC/whitelist required
    "AGGREGATOR_CIRCUIT_BREAKER",  # router temporarily refusing quotes (e.g. Enso 5xx burst)
    "DEPOSIT_CAP_REACHED",         # Aave/Pendle/JLP cap hit
    "POOL_NOT_INITIALIZED",        # V4 / Whirlpool / Raydium CLMM uninitialized poolKey
    "STALE_PRICE_FEED",            # Pyth/Chainlink heartbeat exceeded
    "SUPPLY_CAP_REACHED",          # alias for DEPOSIT_CAP_REACHED at the per-asset Aave level
    "FROZEN_ACCOUNT",              # SPL token-frozen state pre-flight
    "TOKEN_2022_HOOK_UNTRUSTED",   # Token-2022 transfer-hook is not on the allowlist
    "MEV_FORCE_PRIVATE_LANE",      # Shield exposure score forces private bundle (MEVBlocker/Jito)
    "GAS_MODEL_MISMATCH",          # EIP-1559 expected on a chain that only honors legacy gas
    "SELF_TRADE_AGAINST_OWN_LP",   # User-owned LP would be hit by their own prep-swap
    "JIT_ATTACK_ADJACENCY",        # Mempool JIT monitor flagged a sandwich risk
    "POOL_LINK_REDIRECT",          # Adapter unsupported — frontend pool_link card was emitted
    "NEEDS_FRONTEND_SDK",          # Calldata composition needs in-browser SDK (Pendle ApproxParams, etc.)
    # V7-062..V7-065 — UPPER_SNAKE normalization batch. These codes were
    # previously emitted lowercase across the build_*_execution_plan +
    # wallet_swap + execute_pool_position emitters. Normalized to the
    # canonical UPPER_SNAKE form so the recovery dispatcher can do
    # case-sensitive matching without per-emitter casefolding.
    "UNSUPPORTED_ADAPTER",         # Intent picked a protocol with no registered adapter
    "ADAPTER_BUILD_FAILED",        # Adapter raised mid-build (timeout / quote miss / RPC)
    "WALLET_CHAIN_MISMATCH",       # EVM wallet present, Solana plan (or vice versa)
    "INSUFFICIENT_BALANCE",        # Wallet shortfall vs requested amount_in
    "NULL_ROUTE",                  # F09 — DexScreener / aggregator returned no credible route
    "FORBIDDEN_REFUND_SWAP_BACK",  # V7-068 — shield refused an auto-swap-back-of-refund recovery
    "LEDGER_NO_ALT_SUPPORT",       # §13 Row 15 — Ledger/hw wallet can't sign Solana v0 ALT tx
    "DUST_BELOW_THRESHOLD",        # §3 / §6f — position <$1 USD, sweep/leave/increase choice
    "SESSION_KEY_MIRROR_DRIFT",    # §1 inv 5 — on-chain session-key policy diverges from off-chain proposal
    # Fix-wave-3 — §13 spec-scenario blockers (H08/H09/H10/H11/H12/H14 + E15).
    # Each one has a dedicated emitter in
    # src/defi/execution/scenarios/scenario_blockers.py; the build path calls
    # scan_scenario_blockers() once after `steps` are built.
    "PARTIAL_ALLOWANCE_REMAINING", # H08 — allowance > 0 but < amount (USDT non-zero-update quirk)
    "LST_ALREADY_DEPOSITED",       # H10 — wrapped LST already in wallet → skip wrap+swap
    "NFT_LP_REFINANCE_INCOMPLETE", # H11 — refinance intent → multi-step (collect+close+open) missing
    "CLAIM_COMPOUND_INCOMPLETE",   # H12 — claim+compound intent → claim_rewards+reinvest missing
    "V2_TO_V3_MIGRATE_INCOMPLETE", # H14 — V2→V3 migrate intent → remove+add missing
    "PRICE_IMPACT_TOO_HIGH",       # E15 — step price_impact_bps ≥ 500 → refuse status:ready
    "COMPOSED_PLAN_INCOMPLETE_TX", # RC7a — composed-plan step missing signable tx
})


# Lowercase → canonical UPPER_SNAKE aliases. Surfaced by matrix Pass A
# wave 1 (BUG-F-{01..05} + BUG-B-various). Upstream emitters hand-mint
# these strings; the normalizer at `ExecutionPlanV3.add_blocker` maps
# them to the canonical form so the recovery dispatcher's case-sensitive
# match succeeds and KNOWN_BLOCKER_CODES validation passes.
_BLOCKER_CODE_ALIASES: dict[str, str] = {
    "pool_not_found": "UNSUPPORTED_ADAPTER",
    "unsupported_chain": "WALLET_CHAIN_MISMATCH",
    "quote_unavailable": "NULL_ROUTE",
    "missing_allowance": "APPROVAL_MISSING",
    "insufficient_balance": "INSUFFICIENT_BALANCE",
    "gas_top_up": "GAS_TOPUP_REQUIRED",
    "gas_topup": "GAS_TOPUP_REQUIRED",
    "adapter_build_failed": "ADAPTER_BUILD_FAILED",
    "adapter_quote_required": "ADAPTER_QUOTE_REQUIRED",
    "stale_price": "STALE_PRICE_FEED",
    "pool_not_initialized": "POOL_NOT_INITIALIZED",
    "wallet_chain_mismatch": "WALLET_CHAIN_MISMATCH",
    "wallet_not_connected": "WALLET_CHAIN_MISMATCH",  # alias until distinct code lands
    "dust_below_threshold": "DUST_BELOW_THRESHOLD",
}


def _normalize_blocker(blocker: "ExecutionBlocker") -> "ExecutionBlocker":
    """Normalize a blocker's `code` to canonical UPPER_SNAKE form and try
    to attach recovery enrichment when an alias maps to a known code.

    Lowercase + alias variants pass through to KNOWN_BLOCKER_CODES; the
    `_recovery` field attaches a typed-recovery suggestion when the
    blocker's canonical code has a `FailureKind` registered. Failure to
    import recovery helpers (test envs without `src.defi.recovery`) is
    swallowed — normalization is the primary contract.
    """
    raw = (blocker.code or "").strip()
    if not raw:
        return blocker
    if raw in KNOWN_BLOCKER_CODES:
        canonical = raw
    else:
        canonical = _BLOCKER_CODE_ALIASES.get(raw) or _BLOCKER_CODE_ALIASES.get(raw.lower())
        if canonical is None:
            # Last-chance: upper-snake the raw string and accept iff that
            # matches KNOWN_BLOCKER_CODES — otherwise leave as-is so the
            # caller can investigate the unknown code.
            upper = raw.upper()
            if upper in KNOWN_BLOCKER_CODES:
                canonical = upper
            else:
                return blocker
    if canonical == blocker.code:
        return blocker
    return ExecutionBlocker(
        code=canonical,
        severity=blocker.severity,
        title=blocker.title,
        detail=blocker.detail,
        affected_step_ids=list(blocker.affected_step_ids),
        recoverable=blocker.recoverable,
        cta=blocker.cta,
    )


@dataclass
class ExecutionStepV3:
    step_id: str
    index: int
    action: StepAction
    title: str
    description: str
    chain: str
    wallet: WalletKind
    protocol: str
    asset_in: str | None = None
    asset_out: str | None = None
    amount_in: str | None = None
    amount_out: str | None = None
    slippage_bps: int | None = None
    gas_estimate_usd: float | None = None
    duration_estimate_s: int | None = None
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = "pending"
    blocker_codes: list[str] = field(default_factory=list)
    transaction: UnsignedStepTransaction | None = None
    receipt: dict[str, Any] | None = None
    risk_warnings: list[str] = field(default_factory=list)
    # Spec §6c composed-plan primitives (snapshot → rebuild → promote).
    # Populated on bridge / async legs and consumed by the runtime rebuild
    # loop when the upstream step's actual delta lands. None for same-chain
    # synchronous steps.
    snapshot: dict[str, Any] | None = None
    fill_resolved: dict[str, Any] | None = None
    recovery_hook: dict[str, Any] | None = None
    # V7-001 — Confirm-button binding. `simulated_calldata_hash` is
    # stamped at simulation time over the canonical unsigned-tx blob;
    # `broadcast_calldata_hash` is recomputed at the broadcast boundary
    # over what the wallet is about to sign. The state machine refuses
    # any submitted-flip where these diverge.
    simulated_calldata_hash: str | None = None
    broadcast_calldata_hash: str | None = None
    # V7-047 — 30s re-sim freshness window. POSIX timestamp stamped by the
    # simulator when `simulated_calldata_hash` is populated. The broadcast
    # path consults this to decide whether the cached sim is stale and must
    # be refreshed before signing. Optional default-None keeps every legacy
    # construction path (and the V7-001 / V7-010 wire-ups) backwards-compat.
    simulated_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "step_id": self.step_id,
            "index": self.index,
            "action": self.action,
            "title": self.title,
            "description": self.description,
            "chain": self.chain,
            "wallet": self.wallet,
            "protocol": self.protocol,
            "asset_in": self.asset_in,
            "asset_out": self.asset_out,
            "amount_in": self.amount_in,
            "amount_out": self.amount_out,
            "slippage_bps": self.slippage_bps,
            "gas_estimate_usd": self.gas_estimate_usd,
            "duration_estimate_s": self.duration_estimate_s,
            "depends_on": list(self.depends_on),
            "status": self.status,
            "blocker_codes": list(self.blocker_codes),
            "transaction": self.transaction.to_dict() if self.transaction else None,
            "receipt": self.receipt,
            "risk_warnings": list(self.risk_warnings),
        }
        # Composed-plan fields are optional — only surface when populated to
        # keep the wire-format compact for same-chain plans.
        if self.snapshot is not None:
            data["snapshot"] = self.snapshot
        if self.fill_resolved is not None:
            data["fill_resolved"] = self.fill_resolved
        if self.recovery_hook is not None:
            data["recovery_hook"] = self.recovery_hook
        # V7-001 — surface calldata-hash binding so the frontend can
        # display the artifact hash next to the Confirm button and the
        # audit-log can prove signing was hash-bound.
        if self.simulated_calldata_hash is not None:
            data["simulated_calldata_hash"] = self.simulated_calldata_hash
        if self.broadcast_calldata_hash is not None:
            data["broadcast_calldata_hash"] = self.broadcast_calldata_hash
        if self.simulated_at is not None:
            data["simulated_at"] = self.simulated_at
        return data


@dataclass
class ExecutionBlocker:
    code: str
    severity: Literal["info", "warning", "blocker"]
    title: str
    detail: str
    affected_step_ids: list[str] = field(default_factory=list)
    recoverable: bool = True
    cta: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionPlanV3Totals:
    estimated_gas_usd: float = 0.0
    estimated_duration_s: int = 0
    signatures_required: int = 0
    chains_touched: list[str] = field(default_factory=list)
    assets_required: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionPlanV3:
    plan_id: str
    title: str
    summary: str
    status: PlanStatus = "draft"
    risk_gate: RiskGate = "clear"
    requires_double_confirm: bool = False
    blockers: list[ExecutionBlocker] = field(default_factory=list)
    steps: list[ExecutionStepV3] = field(default_factory=list)
    totals: ExecutionPlanV3Totals = field(default_factory=ExecutionPlanV3Totals)
    research_thesis: str | None = None
    strategy_id: str | None = None

    @classmethod
    def new(cls, *, title: str, summary: str, **kwargs: Any) -> "ExecutionPlanV3":
        return cls(plan_id=f"plan_{uuid4().hex[:12]}", title=title, summary=summary, **kwargs)

    def add_step(self, step: ExecutionStepV3) -> None:
        self.steps.append(step)
        self._recompute_totals()
        self._recompute_step_statuses()
        self._refresh_plan_status()

    def add_blocker(self, blocker: ExecutionBlocker) -> None:
        # Matrix Pass A surfaced 5 P0s in category F where upstream emitters
        # (execute_pool_position.py:475, build_yield_execution_plan.py:614/640,
        # swap_simulate.py:150) hand-mint lowercase blocker codes that bypass
        # KNOWN_BLOCKER_CODES + recovery enrichment. Normalize at this
        # chokepoint so future emitters don't have to remember.
        blocker = _normalize_blocker(blocker)
        self.blockers.append(blocker)
        self._recompute_step_statuses()
        if any(b.severity == "blocker" for b in self.blockers):
            self.status = "blocked"

    def _recompute_totals(self) -> None:
        gas = 0.0
        duration = 0
        chains: list[str] = []
        sigs = 0
        assets_req: dict[str, float] = {}
        for step in self.steps:
            if step.gas_estimate_usd:
                gas += float(step.gas_estimate_usd)
            if step.duration_estimate_s:
                duration += int(step.duration_estimate_s)
            if step.chain not in chains:
                chains.append(step.chain)
            if step.action != "wait_receipt" and step.action != "verify_balance":
                sigs += 1
            # Approve steps don't move tokens; skip them in the wallet-holdings
            # roll-up. Same for receipt waits.
            if step.action in {"approve", "wait_receipt", "verify_balance"}:
                continue
            sym = (step.asset_in or "").strip().upper()
            if not sym or sym.startswith("0X") or "+" in sym:
                # Hide hex addresses + compound "USDC+WETH" placeholders.
                continue
            try:
                amt = float(step.amount_in) if step.amount_in is not None else 0.0
            except (TypeError, ValueError):
                amt = 0.0
            if amt <= 0:
                continue
            # MAX across steps, not SUM: a multi-step plan that pre-swaps
            # then mints from the same input shouldn't double-count the
            # wallet requirement (swap leg of 52 USDC + mint of 100 USDC is
            # really still 100 USDC out of the wallet).
            if amt > assets_req.get(sym, 0.0):
                assets_req[sym] = amt
        # Preserve any caller-injected entries (e.g. dual-token V2) but our
        # step-derived numbers win when the same symbol shows up.
        merged: dict[str, str] = dict(self.totals.assets_required or {})
        for sym, amt in assets_req.items():
            # Keep precision sane: trim trailing zeros, fall back to a string
            # the wallet UI can format with locale awareness.
            text = f"{amt:.8f}".rstrip("0").rstrip(".") or "0"
            merged[sym] = text
        self.totals = ExecutionPlanV3Totals(
            estimated_gas_usd=round(gas, 2),
            estimated_duration_s=duration,
            signatures_required=sigs,
            chains_touched=chains,
            assets_required=merged,
        )

    def _recompute_step_statuses(self) -> None:
        blocked_step_ids = {
            step_id
            for blocker in self.blockers
            if blocker.severity == "blocker"
            for step_id in blocker.affected_step_ids
        }
        prior_unconfirmed = False
        first_ready_taken = False
        for step in self.steps:
            if step.step_id in blocked_step_ids:
                step.status = "blocked"
                prior_unconfirmed = True
                continue
            if step.status in {"submitted", "confirmed", "failed", "skipped", "signing"}:
                if step.status not in {"confirmed", "skipped"}:
                    prior_unconfirmed = True
                continue
            if prior_unconfirmed:
                step.status = "pending"
                continue
            if not first_ready_taken:
                step.status = "ready"
                first_ready_taken = True
            else:
                step.status = "pending"
                prior_unconfirmed = True

    def mark_step_status(self, step_id: str, status: StepStatus, *, receipt: dict[str, Any] | None = None) -> None:
        # §11 D.2 — refuse to flip a step to 'submitted' when the cached
        # simulation is older than the 30s freshness window. Plan must store
        # `simulated_at` (POSIX ts) in metadata for the check to fire; absent
        # metadata is a soft-pass so legacy flows keep working.
        if status == "submitted":
            # V7-001 — calldata-hash invariant. Run the bind check first
            # so a tampered/divergent broadcast is hard-blocked before
            # any freshness or drift gates. The target step must carry
            # both `simulated_calldata_hash` and `broadcast_calldata_hash`
            # for the check to fire; absent either side is a hard refusal
            # because we never sign calldata that wasn't bound to a
            # simulation.
            for _step in self.steps:
                if _step.step_id != step_id:
                    continue
                sim_h = _step.simulated_calldata_hash
                bc_h = _step.broadcast_calldata_hash
                if sim_h is not None or bc_h is not None:
                    from src.defi.execution.state_machine import (
                        assert_calldata_match,
                    )
                    assert_calldata_match(
                        sim_h or "",
                        bc_h or "",
                        step_id=step_id,
                        context={"plan_id": self.plan_id},
                    )
                break
            sim_at = getattr(self, "simulated_at", None) or (
                self.totals.assets_required.get("__sim_at__") if self.totals else None
            )
            if sim_at:
                try:
                    sim_ts = float(sim_at)
                except (TypeError, ValueError):
                    sim_ts = 0.0
                if sim_ts > 0:
                    from src.defi.freshness import is_simulation_fresh
                    fr = is_simulation_fresh(sim_ts)
                    if not fr.is_fresh:
                        # Soft-warn + skip the broadcast flip; runtime should
                        # re-simulate and call mark_step_status again with a
                        # fresh sim. Hard-raise when IL_STRICT_STATE=1.
                        import logging
                        import os
                        logging.getLogger(__name__).warning(
                            "freshness refuse: plan=%s step=%s elapsed=%.1fs > %ds",
                            self.plan_id, step_id, fr.elapsed_s, fr.threshold_s,
                        )
                        if os.environ.get("IL_STRICT_STATE") == "1":
                            from src.defi.freshness import assert_fresh_before_broadcast
                            assert_fresh_before_broadcast(sim_ts)
                        return
            # §11 D.7 — explicit price-drift gate. Fires on any broadcast
            # flip with both quotes captured in plan.metadata, independent
            # of D.2 freshness (D.2 is time-based, D.7 is value-based).
            meta = getattr(self, "metadata", None)
            if isinstance(meta, dict):
                sim_quote = meta.get("simulated_quote")
                cur_quote = meta.get("current_quote")
                if sim_quote is not None and cur_quote is not None:
                    from src.defi.freshness import check_price_drift
                    drift = check_price_drift(
                        float(sim_quote), float(cur_quote),
                    )
                    if drift.breached:
                        import logging
                        import os
                        logging.getLogger(__name__).warning(
                            "drift refuse: plan=%s step=%s drift=%.1fbps > %dbps",
                            self.plan_id, step_id, drift.drift_bps,
                            drift.threshold_bps,
                        )
                        if os.environ.get("IL_STRICT_STATE") == "1":
                            from src.defi.freshness import (
                                assert_drift_within_threshold,
                            )
                            assert_drift_within_threshold(
                                float(sim_quote), float(cur_quote),
                            )
                        return
        for step in self.steps:
            if step.step_id == step_id:
                step.status = status
                if receipt is not None:
                    step.receipt = receipt
                break
        self._recompute_step_statuses()
        self._refresh_plan_status()

    def _refresh_plan_status(self) -> None:
        prior = self.status
        if any(step.status == "failed" for step in self.steps):
            new_status = "failed"
        elif all(step.status in {"confirmed", "skipped"} for step in self.steps) and self.steps:
            new_status = "complete"
        elif any(step.status in {"signing", "submitted"} for step in self.steps):
            new_status = "executing"
        elif any(step.status == "ready" for step in self.steps):
            new_status = "ready"
        elif any(b.severity == "blocker" for b in self.blockers):
            new_status = "blocked"
        else:
            return
        if prior != new_status:
            self._validate_pipeline_transition(prior, new_status)
        self.status = new_status

    def _validate_pipeline_transition(self, prior: str, next_status: str) -> None:
        """Spec §5 — refuse silent illegal jumps. Soft-warn first, hard-raise
        when the env flag IL_STRICT_STATE is set, so existing flows don't
        break while wire-in beds in. Maps plan-status → PipelineState then
        defers to src.defi.state_machine.is_legal_transition.

        Projection-jump exceptions: plan-level status is a *coarse* rollup of
        the per-step state machine. When all steps reach `ready` directly
        (deterministic build path that pre-simulated each step), the plan
        legitimately advances draft→ready without ever emitting intermediate
        plan statuses for parsing/resolving/sizing/previewing/shielding/
        simulating. The per-step machine already walked through those; the
        plan-level rollup is just catching up. Same for the draft→blocked
        fast-path when a build-time blocker fires before any step land.
        """
        # Coarse-projection fast-forwards that the per-step machine already
        # justified — admit silently to keep production logs signal-only.
        _projection_jumps = {
            ("draft", "ready"),
            ("draft", "blocked"),
            ("draft", "executing"),
            ("draft", "failed"),
            ("ready", "complete"),  # zero-step plans (e.g. research-only)
            ("blocked", "ready"),   # blocker cleared on user input
            ("blocked", "draft"),   # plan reset for re-prompt
        }
        if (prior, next_status) in _projection_jumps:
            return

        from src.defi.state_machine import PipelineState, is_legal_transition
        prior_state = _PLAN_TO_PIPELINE_STATE.get(prior)
        next_state = _PLAN_TO_PIPELINE_STATE.get(next_status)
        if not prior_state or not next_state:
            return  # initial entry or unmapped → tolerate
        try:
            prior_enum = PipelineState(prior_state)
            next_enum = PipelineState(next_state)
        except ValueError:
            return
        if not is_legal_transition(prior_enum, next_enum):
            import logging
            import os
            msg = (
                f"plan {self.plan_id} illegal state transition "
                f"{prior} ({prior_state}) → {next_status} ({next_state}) — "
                "spec §5 forbids this jump"
            )
            logging.getLogger(__name__).warning(msg)
            if os.environ.get("IL_STRICT_STATE") == "1":
                raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "title": self.title,
            "summary": self.summary,
            "status": self.status,
            "risk_gate": self.risk_gate,
            "requires_double_confirm": self.requires_double_confirm,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "steps": [step.to_dict() for step in self.steps],
            "totals": self.totals.to_dict(),
            "research_thesis": self.research_thesis,
            "strategy_id": self.strategy_id,
        }


# Map plan.status terms → PipelineState (spec §5). Plan-level statuses are
# a coarser projection of the pipeline state machine — this map collapses
# the per-step lifecycle into the canonical spec vocabulary so illegal jumps
# are caught at runtime. Both legacy and canonical (spec §12) vocabularies
# map; the §5 enforcer admits both spellings.
_PLAN_TO_PIPELINE_STATE: dict[str, str] = {
    # Legacy → PipelineState
    "draft": "Prompted",
    "ready": "ReadyToSign",
    "blocked": "Blocked",
    "executing": "Signing",
    "complete": "Indexed",
    "failed": "Failed",
    "aborted": "Cancelled",
    # Canonical §12 → PipelineState
    "DRAFTING": "Prompted",
    "READY_TO_SIGN": "ReadyToSign",
    "SIGNING_IN_PROGRESS": "Signing",
    "BROADCASTED": "Broadcasted",
    "PENDING_DST_FILL": "PendingDstFill",
    "REBUILDING": "Rebuilding",
    "CONFIRMING": "Confirming",
    "VERIFYING": "Verifying",
    "INDEXED": "Indexed",
    "FAILED": "Failed",
    "STUCK_BALANCE": "StuckBalanceFlow",
    "CANCELLED": "Cancelled",
}


def make_step(
    *,
    index: int,
    action: StepAction,
    title: str,
    description: str,
    chain: str,
    wallet: WalletKind,
    protocol: str,
    **kwargs: Any,
) -> ExecutionStepV3:
    return ExecutionStepV3(
        step_id=f"step_{uuid4().hex[:10]}",
        index=index,
        action=action,
        title=title,
        description=description,
        chain=chain,
        wallet=wallet,
        protocol=protocol,
        **kwargs,
    )
