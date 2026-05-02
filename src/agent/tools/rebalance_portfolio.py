"""Chat-callable tool that runs the optimizer path synchronously."""
from __future__ import annotations

from src.agent.planner import build_plan
from src.agent.tools._base import ToolCtx, err_envelope, ok_envelope
from src.optimizer.delta import MoveCandidate, should_move
from src.optimizer.plan_synth import build_rebalance_intent
from src.optimizer.snapshot import snapshot_from_user
from src.optimizer.target_builder import build_target
from src.storage.agent_preferences import get_or_default
from src.storage.database import get_database


async def rebalance_portfolio(
    ctx: ToolCtx,
    *,
    total_usd: float | None = None,
) -> "ToolEnvelope":  # type: ignore[name-defined]
    db = await get_database()
    prefs = await get_or_default(db, ctx.user_id)
    if not prefs.auto_rebalance_opt_in:
        return ok_envelope(
            data={"message": "You haven't opted into auto-rebalancing. Say 'opt in' to enable."},
            card_type="text",
            card_payload={"message": "You haven't opted into auto-rebalancing. Say 'opt in' to enable."},
        )

    holdings = await snapshot_from_user(ctx.wallet or "")
    target = build_target(holdings, risk_budget=prefs.risk_budget, total_usd=total_usd)
    moves = []
    for h, t in zip(holdings, target):
        candidate = MoveCandidate(
            usd_value=t.get("usd", 0),
            apy_delta=t.get("apy", 0) - h.get("apy", 0),
            sentinel_delta=(t.get("sentinel", 0) - h.get("sentinel", 0)),
            estimated_gas_usd=t.get("estimated_gas_usd", 20),
        )
        if should_move(candidate):
            moves.append({"from": h, "to": t, "candidate": candidate})

    if not moves:
        return ok_envelope(
            data={"message": "No changes needed. Your current positions are optimal."},
            card_type="text",
            card_payload={"message": "No changes needed. Your current positions are optimal."},
        )

    intent = build_rebalance_intent(moves)
    try:
        plan = build_plan(intent)
    except Exception as exc:
        return err_envelope("rebalance_failed", str(exc))

    return ok_envelope(
        data=plan.model_dump(),
        card_type="execution_plan_v2",
        card_payload=plan.model_dump(),
    )
