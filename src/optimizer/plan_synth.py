"""Translate optimizer moves into the same intent shape that compose_plan expects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.api.schemas.agent import ExecutionPlanV2Payload
from src.agent.planner import build_plan


@dataclass(frozen=True)
class RebalancePlanCard:
    card_type: str
    payload: ExecutionPlanV2Payload


def move_to_plan(move: dict[str, Any]) -> RebalancePlanCard:
    token = str(move.get("from_token") or "USDC")
    chain_id = int(move.get("to_chain_id") or 42161)
    protocol = str(move.get("to_protocol") or "aave-v3")
    plan = build_plan(
        {
            "title": f"Rebalance {token} to {protocol}",
            "steps": [
                {
                    "step_id": "stake",
                    "action": "stake",
                    "params": {
                        "token": token,
                        "protocol": protocol,
                        "chain_id": chain_id,
                        "amount_usd": float(move.get("usd_value") or 0),
                        "estimated_gas_usd": float(move.get("estimated_gas_usd") or 0),
                    },
                }
            ],
        }
    )
    return RebalancePlanCard(card_type="execution_plan_v2", payload=plan)


def build_rebalance_intent(moves: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a plan intent from optimizer delta moves."""
    steps: list[dict[str, Any]] = []
    for i, move in enumerate(moves, start=1):
        to = move.get("to") or {}
        steps.append({
            "action": "stake" if to.get("apy", 0) > 0 else "transfer",
            "params": {
                "token": to.get("token", "?"),
                "protocol": to.get("protocol", "?"),
                "chain_id": to.get("chain_id", 1),
                "amount": str(to.get("usd", "0")),
                "amount_usd": to.get("usd", 0),
            },
        })
    return {
        "title": "Portfolio rebalance",
        "steps": steps,
    }
