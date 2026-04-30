from __future__ import annotations

from uuid import uuid4

from src.api.schemas.agent import ExecutionPlanV2Payload, PlanStepV2
from src.scoring.bridge_scorer import score_bridge_mapping
from src.scoring.pool_scorer import score_pool_mapping
from src.scoring.route_scorer import score_route_mapping
from src.scoring.shield_gate import shield_for_transaction


EVM_ERC20_ACTIONS = {"bridge", "deposit_lp", "swap"}
NATIVE_SYMBOLS = {"", "ETH", "BNB", "MATIC", "AVAX", "SOL", "NATIVE"}
NON_EVM_CHAIN_IDS = {0, 101, 7565164}
MAX_EXPLICIT_STEPS = 4


def _needs_approval(action: str, params: dict) -> bool:
    token = str(params.get("token_in") or params.get("token") or params.get("token_symbol") or "").upper()
    chain_id = int(params.get("src_chain_id") or params.get("chain_id") or 0)
    return action in EVM_ERC20_ACTIONS and chain_id not in NON_EVM_CHAIN_IDS and token not in NATIVE_SYMBOLS


def _chain_touch(params: dict) -> list[str]:
    chains = []
    for key in ("src_chain_id", "dst_chain_id", "chain_id"):
        if key in params:
            chains.append(str(params[key]))
    return chains


def _estimated_gas(action: str) -> float:
    if action in {"bridge", "swap", "stake", "deposit_lp"}:
        return 8.0
    if action == "approve":
        return 2.0
    return 0.0


def _estimated_seconds(action: str) -> int:
    if action in {"bridge", "wait_receipt"}:
        return 90
    if action in {"swap", "stake", "deposit_lp", "approve", "transfer"}:
        return 30
    return 0


def _amount_usd(params: dict) -> float:
    try:
        return float(params.get("amount_usd") or params.get("notional_usd") or 0)
    except (TypeError, ValueError):
        return 0.0


def _pool_source(action: str, params: dict) -> dict:
    token = str(params.get("token") or params.get("token_out") or "USDC")
    protocol = str(params.get("protocol") or params.get("project") or ("curve" if action == "deposit_lp" else "aave-v3"))
    return {
        "project": protocol,
        "symbol": token,
        "chain": str(params.get("chain") or params.get("chain_id") or "Ethereum"),
        "tvlUsd": params.get("tvlUsd") or 800_000_000,
        "apy": params.get("apy") or (4.8 if action == "stake" else 3.5),
        "stablecoin": any(stable in token.upper() for stable in ("USDC", "USDT", "DAI")),
        "ilRisk": "yes" if action == "deposit_lp" and "/" not in token and "-" not in token else "no",
    }


def _apply_step_risk(step: PlanStepV2) -> tuple[list[str], bool]:
    warnings: list[str] = []
    hard_block = False
    if step.action in {"stake", "deposit_lp"}:
        step.sentinel = score_pool_mapping(_pool_source(step.action, step.params))
        if step.sentinel.sentinel < 65:
            warnings.append(f"Step {step.order} Sentinel score below 65")
    elif step.action == "swap":
        sentinel, shield = score_route_mapping(step.params)
        step.sentinel = sentinel
        step.shield_flags = shield.reasons
        if shield.verdict == "SCAM":
            hard_block = True
            warnings.extend(shield.reasons)
    elif step.action == "bridge":
        sentinel, shield = score_bridge_mapping(step.params)
        step.sentinel = sentinel
        step.shield_flags = shield.reasons
        warnings.append("Cross-chain execution requires receipt confirmation before follow-up steps.")
    elif step.action in {"approve", "transfer"}:
        shield = shield_for_transaction(step.params)
        step.shield_flags = shield.reasons
        if shield.verdict == "SCAM":
            hard_block = True
            warnings.extend(shield.reasons)
    return warnings, hard_block


def build_plan(intent: dict) -> ExecutionPlanV2Payload:
    plan_id = str(uuid4())
    raw_steps = intent.get("steps") or []
    if len(raw_steps) > MAX_EXPLICIT_STEPS:
        raw_steps = raw_steps[:MAX_EXPLICIT_STEPS]
        capped = True
    else:
        capped = False
    steps: list[PlanStepV2] = []
    risk_warnings: list[str] = []
    chains_touched: list[str] = []
    previous_step_id: str | None = None

    for index, raw in enumerate(raw_steps):
        action = str(raw["action"])
        params = dict(raw.get("params") or {})
        chains_touched.extend(_chain_touch(params))

        if _needs_approval(action, params):
            approve_id = str(uuid4())
            steps.append(
                PlanStepV2(
                    step_id=approve_id,
                    order=len(steps) + 1,
                    action="approve",
                    params={
                        "token": params.get("token_in") or params.get("token") or params.get("token_symbol"),
                        "amount": params.get("amount", "all"),
                        "chain_id": params.get("src_chain_id") or params.get("chain_id"),
                    },
                    depends_on=[] if previous_step_id is None else [previous_step_id],
                    status="ready" if previous_step_id is None else "pending",
                    estimated_gas_usd=_estimated_gas("approve"),
                    estimated_duration_s=_estimated_seconds("approve"),
                )
            )
            previous_step_id = approve_id

        step_id = str(raw.get("step_id") or uuid4())
        steps.append(
            PlanStepV2(
                step_id=step_id,
                order=len(steps) + 1,
                action=action,
                params=params,
                depends_on=[] if previous_step_id is None else [previous_step_id],
                resolves_from=dict(raw.get("resolves_from") or {}),
                status="ready" if previous_step_id is None else "pending",
                estimated_gas_usd=_estimated_gas(action),
                estimated_duration_s=_estimated_seconds(action),
            )
        )
        previous_step_id = step_id

        if action == "bridge":
            if index < len(raw_steps) - 1:
                wait_id = str(uuid4())
                steps.append(
                    PlanStepV2(
                        step_id=wait_id,
                        order=len(steps) + 1,
                        action="wait_receipt",
                        params={"source_step_id": step_id},
                        depends_on=[step_id],
                        status="pending",
                        estimated_gas_usd=_estimated_gas("wait_receipt"),
                        estimated_duration_s=_estimated_seconds("wait_receipt"),
                    )
                )
                previous_step_id = wait_id

    for order, step in enumerate(steps, start=1):
        step.order = order

    hard_block = False
    for step in steps:
        warnings, blocked = _apply_step_risk(step)
        risk_warnings.extend(warnings)
        hard_block = hard_block or blocked

    if capped:
        risk_warnings.append("Planner capped at 4 explicit steps; split the remaining actions into a second plan.")

    total_gas = sum(step.estimated_gas_usd or 0 for step in steps)
    sentinel_steps = [step.sentinel.sentinel for step in steps if step.sentinel is not None]
    blended_sentinel = round(sum(sentinel_steps) / len(sentinel_steps)) if sentinel_steps else None
    large_notional = any(_amount_usd(step.params) >= 10_000 for step in steps)
    risk_gate = "hard_block" if hard_block else ("soft_warn" if risk_warnings or large_notional or (blended_sentinel is not None and blended_sentinel < 65) else "clear")
    return ExecutionPlanV2Payload(
        plan_id=plan_id,
        title=str(intent.get("title") or "Execution plan"),
        steps=steps,
        total_steps=len(steps),
        total_gas_usd=total_gas,
        total_duration_estimate_s=sum(step.estimated_duration_s or 0 for step in steps),
        blended_sentinel=blended_sentinel,
        requires_signature_count=0 if risk_gate == "hard_block" else sum(1 for step in steps if step.action not in {"wait_receipt", "get_balance"}),
        risk_warnings=risk_warnings,
        risk_gate=risk_gate,
        requires_double_confirm=risk_gate == "soft_warn",
        chains_touched=sorted(set(chains_touched)),
        user_assets_required={},
    )
