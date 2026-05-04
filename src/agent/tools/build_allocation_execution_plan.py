"""Compose ONE ExecutionPlanV3 from a list of allocation rows.

Triggered by follow-ups like "execute the transactions through my wallet" /
"execute the strategy" after `allocate_plan` produced N pools the user wants
to deposit into. Each row produces its own deposit step (and any prerequisite
approve / swap / bridge), all dependency-linked into a single signable plan.
"""
from __future__ import annotations

import re
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


_CHAIN_ALIAS = {
    "eth": "ethereum",
    "ether": "ethereum",
    "arb": "arbitrum",
    "arbi": "arbitrum",
    "op": "optimism",
    "opt": "optimism",
    "matic": "polygon",
    "poly": "polygon",
    "avax": "avalanche",
    "bnb": "bsc",
    "bsc": "bsc",
    "base": "base",
    "ethereum": "ethereum",
    "polygon": "polygon",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "avalanche": "avalanche",
    "solana": "solana",
    "sol": "solana",
}


def _coerce(amount: Any) -> Decimal:
    if amount is None:
        return Decimal(0)
    raw = str(amount).strip()
    if not raw:
        return Decimal(0)
    # strip currency markers commonly present in allocate_plan output ($70, "70 USDC")
    cleaned = raw.replace("$", "").replace(",", "").strip()
    parts = cleaned.split()
    if parts:
        cleaned = parts[0]
    try:
        return Decimal(cleaned)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _normalize_chain(value: Any) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    return _CHAIN_ALIAS.get(s, s)


def _normalize_protocol(value: Any) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    s = s.replace(" ", "-").replace("_", "-")
    # Strip duplicate hyphens.
    while "--" in s:
        s = s.replace("--", "-")
    return s


def _row_amount(row: dict[str, Any], total_hint: Decimal | None = None) -> Decimal:
    for key in ("amount_in", "deposit_amount", "amount_usd", "allocation_usd", "usd", "usd_amount", "amount"):
        v = row.get(key)
        if v is None:
            continue
        amt = _coerce(v)
        if amt > 0:
            return amt
    # Fall back to weight*total split (allocate_plan emits weight as a percent
    # and the chat caller may pass total_hint via default_amount_total).
    weight = row.get("weight") or row.get("share_pct") or row.get("allocation_pct")
    if weight is not None and total_hint is not None and total_hint > 0:
        try:
            pct = Decimal(str(weight)) / Decimal(100)
            return (total_hint * pct).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            pass
    return Decimal(0)


def _row_entry_asset(row: dict[str, Any], default_asset: str | None) -> str:
    explicit = row.get("asset_in") or row.get("deposit_asset")
    if explicit:
        return str(explicit).upper()
    pair = row.get("symbol") or row.get("pair") or row.get("asset")
    if isinstance(pair, str) and pair:
        # Pair like "WETH-USDC" → first leg is the deposit asset for LP routes.
        first_leg = re.split(r"[-/]", pair)[0]
        if first_leg:
            return first_leg.upper()
    return (default_asset or "USDC").upper()


def _row_action(row: dict[str, Any]) -> str:
    explicit = row.get("action")
    if isinstance(explicit, str) and explicit:
        return explicit.lower()
    pt = (row.get("product_type") or "").lower()
    if pt in {"pool", "lp", "amm", "clmm"}:
        return "deposit_lp"
    if pt in {"staking", "stake", "lst"}:
        return "stake"
    sym = (row.get("symbol") or row.get("asset") or "").upper()
    if "-" in sym or "/" in sym:
        return "deposit_lp"
    return "supply"


async def build_allocation_execution_plan(
    ctx,
    *,
    allocations: list[dict[str, Any]],
    user_address: str | None = None,
    default_asset: str | None = "USDC",
    default_amount_total: Any = None,
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
    total_hint = _coerce(default_amount_total)

    for idx, row in enumerate(allocations, start=1):
        chain = _normalize_chain(row.get("chain"))
        protocol = _normalize_protocol(row.get("protocol"))
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
        asset_in = _row_entry_asset(row, default_asset)
        amount = _row_amount(row, total_hint=total_hint or None)
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
