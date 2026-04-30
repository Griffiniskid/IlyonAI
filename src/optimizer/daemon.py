from __future__ import annotations

from dataclasses import dataclass

from src.optimizer.delta import MoveCandidate, should_move
from src.optimizer.plan_synth import RebalancePlanCard, move_to_plan
from src.optimizer.snapshot import PortfolioPosition, PortfolioSnapshot


@dataclass(frozen=True)
class OptimizerRun:
    user_id: int
    outcome: str
    plan: RebalancePlanCard | None = None


class OptimizerDaemon:
    def propose(
        self,
        *,
        user_id: int,
        snapshot: PortfolioSnapshot,
        target_positions: list[PortfolioPosition],
    ) -> OptimizerRun:
        best_move: dict | None = None
        for target in target_positions:
            current = next((pos for pos in snapshot.positions if pos.token == target.token), None)
            if current is None:
                continue
            candidate = MoveCandidate(
                usd_value=current.usd_value,
                apy_delta=target.apy - current.apy,
                sentinel_delta=target.sentinel - current.sentinel,
                estimated_gas_usd=8,
            )
            if should_move(candidate):
                best_move = {
                    "from_token": current.token,
                    "to_protocol": target.protocol,
                    "to_chain_id": 42161,
                    "usd_value": current.usd_value,
                    "estimated_gas_usd": candidate.estimated_gas_usd,
                }
                break
        if best_move is None:
            return OptimizerRun(user_id=user_id, outcome="no_change")
        return OptimizerRun(user_id=user_id, outcome="proposed", plan=move_to_plan(best_move))
