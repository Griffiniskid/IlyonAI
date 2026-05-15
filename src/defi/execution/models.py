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
]
StepStatus = Literal[
    "blocked", "pending", "ready", "signing", "submitted", "confirmed", "failed", "skipped"
]
PlanStatus = Literal[
    "draft", "blocked", "ready", "executing", "complete", "failed", "aborted"
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
})


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
        """
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
# are caught at runtime.
_PLAN_TO_PIPELINE_STATE: dict[str, str] = {
    "draft": "Prompted",
    "ready": "ReadyToSign",
    "blocked": "Blocked",
    "executing": "Signing",
    "complete": "Indexed",
    "failed": "Failed",
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
