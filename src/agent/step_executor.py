from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.api.schemas.agent import ExecutionPlanV2Payload, PlanCompleteFrame, StepStatusFrame


@dataclass
class StoredPlan:
    user_id: int
    payload: ExecutionPlanV2Payload
    status: str
    updated_at: datetime


class PlanExecutionStore:
    def __init__(self) -> None:
        self._plans: dict[str, StoredPlan] = {}

    def save(self, user_id: int, plan: ExecutionPlanV2Payload, *, status: str = "active") -> StoredPlan:
        stored = StoredPlan(user_id=user_id, payload=plan, status=status, updated_at=datetime.now(timezone.utc))
        self._plans[plan.plan_id] = stored
        return stored

    def load(self, plan_id: str) -> StoredPlan | None:
        return self._plans.get(plan_id)

    def update_status(self, plan_id: str, status: str) -> None:
        stored = self._plans[plan_id]
        stored.status = status
        stored.updated_at = datetime.now(timezone.utc)


class StepExecutor:
    def __init__(self, store: PlanExecutionStore) -> None:
        self._store = store

    def save_plan(self, *, user_id: int, plan: ExecutionPlanV2Payload) -> StoredPlan:
        return self._store.save(user_id, plan)

    def _stored(self, plan_id: str) -> StoredPlan:
        stored = self._store.load(plan_id)
        if stored is None:
            raise KeyError(f"unknown plan {plan_id}")
        return stored

    def _step_frame(self, plan: ExecutionPlanV2Payload, step_id: str) -> StepStatusFrame:
        step = next(step for step in plan.steps if step.step_id == step_id)
        return StepStatusFrame(plan_id=plan.plan_id, step_id=step.step_id, order=step.order, status=step.status, tx_hash=step.tx_hash, error=step.error)

    def mark_broadcast(self, plan_id: str, step_id: str, tx_hash: str) -> list[StepStatusFrame]:
        stored = self._stored(plan_id)
        step = next(step for step in stored.payload.steps if step.step_id == step_id)
        step.status = "broadcast"
        step.tx_hash = tx_hash
        return [self._step_frame(stored.payload, step_id)]

    def confirm_step(self, plan_id: str, step_id: str, receipt: dict[str, Any]) -> list[StepStatusFrame]:
        stored = self._stored(plan_id)
        plan = stored.payload
        step = next(step for step in plan.steps if step.step_id == step_id)
        step.status = "confirmed"
        step.receipt = receipt
        frames = [self._step_frame(plan, step_id)]
        for candidate in plan.steps:
            if candidate.status == "pending" and all(
                next(prev for prev in plan.steps if prev.step_id == dep).status == "confirmed"
                for dep in candidate.depends_on
            ):
                candidate.status = "ready"
                frames.append(self._step_frame(plan, candidate.step_id))
                break
        if all(step.status in {"confirmed", "skipped"} for step in plan.steps):
            self._store.update_status(plan_id, "complete")
        return frames

    def abort_plan(self, plan_id: str, reason: str) -> list[StepStatusFrame | PlanCompleteFrame]:
        stored = self._stored(plan_id)
        for step in stored.payload.steps:
            if step.status in {"pending", "ready", "signing", "broadcast"}:
                step.status = "skipped"
                step.error = reason
        self._store.update_status(plan_id, "aborted")
        return [PlanCompleteFrame(plan_id=plan_id, status="aborted", payload={"status": "aborted", "reason": reason})]

    def resume_plan(self, plan_id: str) -> ExecutionPlanV2Payload:
        return self._stored(plan_id).payload
