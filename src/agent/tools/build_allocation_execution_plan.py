"""Compose ONE ExecutionPlanV3 from a list of allocation rows.

Triggered by follow-ups like "execute the transactions through my wallet" /
"execute the strategy" after `allocate_plan` produced N pools the user wants
to deposit into. Each row produces its own deposit step (and any prerequisite
approve / swap / bridge), all dependency-linked into a single signable plan.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from src.agent.tools._base import err_envelope, ok_envelope
from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.capabilities import build_default_registry
from src.defi.execution.models import (
    ExecutionBlocker,
    ExecutionPlanV3,
    ExecutionStepV3,
)
from src.defi.strategy.memory import StrategyRecord, remember_strategy


def _coerce(amount: Any) -> Decimal:
    try:
        return Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _row_amount(row: dict[str, Any]) -> Decimal:
    for key in ("amount_in", "deposit_amount", "amount_usd", "allocation_usd", "amount"):
        v = row.get(key)
        if v is None:
            continue
        amt = _coerce(v)
        if amt > 0:
            return amt
    return Decimal(0)


def _row_asset(row: dict[str, Any], default_asset: str | None) -> str:
    asset = row.get("asset_in") or row.get("deposit_asset") or row.get("asset") or default_asset or "USDC"
    return str(asset).upper()


def _row_action(row: dict[str, Any]) -> str:
    pt = (row.get("product_type") or "").lower()
    if pt in {"pool", "lp", "amm", "clmm"}:
        return "deposit_lp"
    if pt in {"staking", "stake", "lst"}:
        return "stake"
    return "supply"


async def build_allocation_execution_plan(
    ctx,
    *,
    allocations: list[dict[str, Any]],
    user_address: str | None = None,
    default_asset: str | None = "USDC",
    slippage_bps: int = 50,
    research_thesis: str | None = None,
    title_hint: str | None = None,
):
    if not user_address:
        wallet = getattr(ctx, "wallet", None)
        if wallet:
            user_address = str(wallet)
    if not user_address:
        return err_envelope(
            "missing_wallet",
            "Connect a wallet before requesting a multi-pool execution plan.",
        )

    if not allocations:
        return err_envelope(
            "missing_allocations",
            "Pass `allocations` (list of {chain,protocol,action,asset_in,amount_in}) or run `allocate_plan` first.",
        )

    registry = build_default_registry()
    plan = ExecutionPlanV3.new(
        title=title_hint or f"Allocation execution ({len(allocations)} pools)",
        summary=f"Sign each step in your wallet — one deposit per pool ({len(allocations)} total).",
        research_thesis=research_thesis,
    )

    last_step_id_per_chain: dict[str, str] = {}
    succeeded = 0
    constraints: list[dict[str, Any]] = []

    for idx, row in enumerate(allocations, start=1):
        chain = str(row.get("chain") or "").lower().strip()
        protocol = str(row.get("protocol") or "").lower().strip()
        if not chain or not protocol:
            plan.add_blocker(ExecutionBlocker(
                code="row_missing_fields",
                severity="warning",
                title=f"Row {idx} skipped",
                detail="Missing chain/protocol — re-run allocate_plan or provide them explicitly.",
                affected_step_ids=[],
            ))
            continue

        action = _row_action(row)
        asset_in = _row_asset(row, default_asset)
        amount = _row_amount(row)
        if amount <= 0:
            plan.add_blocker(ExecutionBlocker(
                code="row_missing_amount",
                severity="warning",
                title=f"Row {idx} ({protocol} {row.get('symbol') or asset_in}) skipped",
                detail="Amount missing — split a USD total via allocate_plan or pass amount_in per row.",
                affected_step_ids=[],
            ))
            continue

        capability = registry.find(chain=chain, protocol=protocol, action=action)
        if not capability.supported:
            plan.add_blocker(ExecutionBlocker(
                code="unsupported_adapter",
                severity="warning",
                title=f"Row {idx} ({protocol} on {chain}) not yet executable",
                detail=capability.reason or "No verified adapter for this protocol/action/chain.",
                affected_step_ids=[],
            ))
            continue

        adapter = registry.adapter_for(chain=chain, protocol=protocol, action=action)
        assert adapter is not None
        try:
            steps = await adapter.build(YieldBuildRequest(
                chain=chain,
                protocol=protocol,
                asset_in=asset_in,
                amount_in=amount,
                user_address=user_address,
                slippage_bps=slippage_bps,
            ))
        except Exception as exc:
            plan.add_blocker(ExecutionBlocker(
                code="adapter_build_failed",
                severity="warning",
                title=f"Row {idx} ({protocol} on {chain}) skipped",
                detail=str(exc)[:240],
                affected_step_ids=[],
            ))
            continue

        prev_id = last_step_id_per_chain.get(chain)
        first_added: ExecutionStepV3 | None = None
        for step in steps:
            if prev_id and not step.depends_on:
                step.depends_on = [prev_id]
            plan.add_step(step)
            if first_added is None:
                first_added = step
            last_step_id_per_chain[chain] = step.step_id
        succeeded += 1
        constraints.append({
            "chain": chain,
            "protocol": protocol,
            "action": action,
            "asset_in": asset_in,
            "amount_in": str(amount),
        })

    if succeeded == 0:
        plan.add_blocker(ExecutionBlocker(
            code="no_executable_rows",
            severity="blocker",
            title="No row produced an executable step",
            detail="Every allocation row was either unsupported or missing data.",
            affected_step_ids=[],
            cta="Re-run allocate_plan with adapter-supported chains/protocols (Aave V3, Compound V3, Yearn, Lido, Raydium, Marinade, etc.).",
        ))

    session_id = getattr(ctx, "session_id", None)
    if session_id and constraints:
        remember_strategy(StrategyRecord(
            session_id=str(session_id),
            chat_id=str(session_id),
            user_address=user_address,
            intent_summary=f"Multi-pool allocation execution ({succeeded}/{len(allocations)} rows)",
            plan=plan.to_dict(),
            constraints={"allocation_rows": constraints},
        ))

    return ok_envelope(
        data={
            "plan": plan.to_dict(),
            "executable_count": succeeded,
            "total_rows": len(allocations),
        },
        card_type="execution_plan_v3",
        card_payload=plan.to_dict(),
    )
