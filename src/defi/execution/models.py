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
        for step in self.steps:
            if step.gas_estimate_usd:
                gas += float(step.gas_estimate_usd)
            if step.duration_estimate_s:
                duration += int(step.duration_estimate_s)
            if step.chain not in chains:
                chains.append(step.chain)
            if step.action != "wait_receipt" and step.action != "verify_balance":
                sigs += 1
        self.totals = ExecutionPlanV3Totals(
            estimated_gas_usd=round(gas, 2),
            estimated_duration_s=duration,
            signatures_required=sigs,
            chains_touched=chains,
            assets_required=self.totals.assets_required,
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
        for step in self.steps:
            if step.step_id == step_id:
                step.status = status
                if receipt is not None:
                    step.receipt = receipt
                break
        self._recompute_step_statuses()
        self._refresh_plan_status()

    def _refresh_plan_status(self) -> None:
        if any(step.status == "failed" for step in self.steps):
            self.status = "failed"
            return
        if all(step.status in {"confirmed", "skipped"} for step in self.steps) and self.steps:
            self.status = "complete"
            return
        if any(step.status in {"signing", "submitted"} for step in self.steps):
            self.status = "executing"
            return
        if any(step.status == "ready" for step in self.steps):
            self.status = "ready"
            return
        if any(b.severity == "blocker" for b in self.blockers):
            self.status = "blocked"

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
