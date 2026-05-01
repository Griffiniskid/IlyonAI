"""SQLite-backed in-flight plan execution store."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.api.schemas.agent import (
    ExecutionPlanV2Payload,
    PlanCompleteFrame,
    StepStatusFrame,
)
from src.storage.agent_plans import (
    StoredPlan,
    list_active_plans,
    load_plan,
    save_plan,
    update_step_status,
)
from src.storage.database import Database


class PlanExecutionStore:
    """Wrapper around `src.storage.agent_plans` with the API the runtime expects."""

    def __init__(self, db: Database | None = None) -> None:
        self._db = db
        self._plans: dict[str, StoredPlan] = {}

    async def save(
        self,
        user_id: int,
        plan: ExecutionPlanV2Payload,
        *,
        status: str = "active",
    ) -> StoredPlan:
        if self._db is not None:
            return await save_plan(self._db, user_id=user_id, payload=plan, status=status)
        stored = StoredPlan(
            plan_id=plan.plan_id,
            user_id=user_id,
            payload=plan,
            status=status,
            updated_at=datetime.now(timezone.utc),
        )
        self._plans[plan.plan_id] = stored
        return stored

    async def load(self, plan_id: str) -> StoredPlan | None:
        if self._db is not None:
            return await load_plan(self._db, plan_id=plan_id)
        return self._plans.get(plan_id)

    async def list_active(self, user_id: int) -> list[StoredPlan]:
        if self._db is not None:
            return await list_active_plans(self._db, user_id=user_id)
        return [p for p in self._plans.values() if p.user_id == user_id and p.status == "active"]

    async def update_step(
        self,
        plan_id: str,
        step_id: str,
        status: str,
        tx_hash: str | None = None,
        receipt: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> StoredPlan | None:
        if self._db is not None:
            return await update_step_status(
                self._db,
                plan_id=plan_id,
                step_id=step_id,
                status=status,
                tx_hash=tx_hash,
                receipt=receipt,
                error=error,
            )
        stored = self._plans.get(plan_id)
        if stored is None:
            return None
        for step in stored.payload.steps:
            if step.step_id == step_id:
                step.status = status
                if tx_hash is not None:
                    step.tx_hash = tx_hash
                if receipt is not None:
                    step.receipt = receipt
                if error is not None:
                    step.error = error
                break
        stored.updated_at = datetime.now(timezone.utc)
        return stored

    async def update_status(self, plan_id: str, status: str) -> None:
        if self._db is not None:
            from sqlalchemy import update
            from src.storage.database import AgentPlanRow
            async with self._db.async_session() as session:
                await session.execute(
                    update(AgentPlanRow)
                    .where(AgentPlanRow.plan_id == plan_id)
                    .values(status=status, updated_at=datetime.utcnow())
                )
                await session.commit()
            return
        stored = self._plans.get(plan_id)
        if stored is None:
            raise KeyError(f"unknown plan {plan_id}")
        stored.status = status
        stored.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def step_status_frame(
        plan_id: str,
        step_id: str,
        status: str,
        order: int,
        tx_hash: str | None = None,
        error: str | None = None,
    ) -> StepStatusFrame:
        return StepStatusFrame(
            plan_id=plan_id,
            step_id=step_id,
            status=status,  # type: ignore[arg-type]
            order=order,
            tx_hash=tx_hash,
            error=error,
        )

    @staticmethod
    def plan_complete_frame(
        plan_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> PlanCompleteFrame:
        return PlanCompleteFrame(
            plan_id=plan_id,
            status=status,  # type: ignore[arg-type]
            payload=payload,
        )


class StepExecutor:
    def __init__(self, store: PlanExecutionStore) -> None:
        self._store = store

    async def save_plan(self, *, user_id: int, plan: ExecutionPlanV2Payload) -> StoredPlan:
        return await self._store.save(user_id, plan)

    async def _stored(self, plan_id: str) -> StoredPlan:
        stored = await self._store.load(plan_id)
        if stored is None:
            raise KeyError(f"unknown plan {plan_id}")
        return stored

    def _step_frame(self, plan: ExecutionPlanV2Payload, step_id: str) -> StepStatusFrame:
        step = next(step for step in plan.steps if step.step_id == step_id)
        return PlanExecutionStore.step_status_frame(
            plan_id=plan.plan_id,
            step_id=step.step_id,
            status=step.status,
            order=step.order,
            tx_hash=step.tx_hash,
            error=step.error,
        )

    async def mark_broadcast(self, plan_id: str, step_id: str, tx_hash: str) -> list[StepStatusFrame]:
        await self._store.update_step(plan_id, step_id, status="broadcast", tx_hash=tx_hash)
        stored = await self._stored(plan_id)
        return [self._step_frame(stored.payload, step_id)]

    async def confirm_step(self, plan_id: str, step_id: str, receipt: dict[str, Any]) -> list[StepStatusFrame]:
        await self._store.update_step(plan_id, step_id, status="confirmed", receipt=receipt)
        stored = await self._stored(plan_id)
        plan = stored.payload
        frames = [self._step_frame(plan, step_id)]
        for candidate in plan.steps:
            if candidate.status == "pending" and all(
                next(prev for prev in plan.steps if prev.step_id == dep).status == "confirmed"
                for dep in candidate.depends_on
            ):
                await self._store.update_step(plan_id, candidate.step_id, status="ready")
                stored = await self._stored(plan_id)
                frames.append(self._step_frame(stored.payload, candidate.step_id))
                break
        if all(step.status in {"confirmed", "skipped"} for step in stored.payload.steps):
            await self._store.update_status(plan_id, "complete")
        return frames

    async def abort_plan(self, plan_id: str, reason: str) -> list[StepStatusFrame | PlanCompleteFrame]:
        stored = await self._stored(plan_id)
        for step in stored.payload.steps:
            if step.status in {"pending", "ready", "signing", "broadcast"}:
                await self._store.update_step(plan_id, step.step_id, status="skipped", error=reason)
        await self._store.update_status(plan_id, "aborted")
        return [PlanCompleteFrame(plan_id=plan_id, status="aborted", payload={"status": "aborted", "reason": reason})]

    async def resume_plan(self, plan_id: str) -> ExecutionPlanV2Payload:
        return (await self._stored(plan_id)).payload
