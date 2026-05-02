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


def build_rebalance_intent(moves: list[dict]) -> dict:
    """Placeholder — Task 3.2 replaces with real intent synthesis."""
    raise NotImplementedError("build_rebalance_intent not yet implemented")
