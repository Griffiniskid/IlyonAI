"""Agent plans storage layer.

Provides CRUD operations for persisted execution plans.
Uses SQLAlchemy async with SQLite/PostgreSQL compatibility.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update

from src.storage.database import Database, AgentPlanRow
from src.api.schemas.agent import ExecutionPlanV2Payload


@dataclass
class StoredPlan:
    """Lightweight representation of a persisted execution plan."""
    plan_id: str
    user_id: int
    payload: ExecutionPlanV2Payload
    status: str
    updated_at: datetime


async def save_plan(
    db: Database,
    user_id: int,
    payload: ExecutionPlanV2Payload,
    status: str,
    expires_at: Optional[datetime] = None,
) -> StoredPlan:
    """Persist an ExecutionPlanV2Payload and return a StoredPlan.

    Args:
        db: Database instance
        user_id: User identifier
        payload: Execution plan payload to persist
        status: Plan status (e.g., 'active', 'complete', 'failed')
        expires_at: Optional expiration timestamp

    Returns:
        StoredPlan with the persisted data
    """
    plan_id = payload.plan_id
    now = datetime.utcnow()
    payload_json = payload.model_dump_json()

    async with db.async_session() as session:
        row = AgentPlanRow(
            plan_id=plan_id,
            user_id=user_id,
            payload_json=payload_json,
            status=status,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        session.add(row)
        await session.commit()

        return StoredPlan(
            plan_id=plan_id,
            user_id=user_id,
            payload=payload,
            status=status,
            updated_at=now,
        )


async def load_plan(db: Database, plan_id: str) -> Optional[StoredPlan]:
    """Load a plan by plan_id.

    Args:
        db: Database instance
        plan_id: Plan identifier

    Returns:
        StoredPlan if found, None otherwise
    """
    async with db.async_session() as session:
        result = await session.execute(
            select(AgentPlanRow).where(AgentPlanRow.plan_id == plan_id)
        )
        row = result.scalar_one_or_none()

        if row is None:
            return None

        payload = ExecutionPlanV2Payload.model_validate_json(row.payload_json)

        return StoredPlan(
            plan_id=row.plan_id,
            user_id=row.user_id,
            payload=payload,
            status=row.status,
            updated_at=row.updated_at,
        )


async def list_active_plans(db: Database, user_id: int) -> List[StoredPlan]:
    """Return active (non-expired, status='active') plans for a user.

    Args:
        db: Database instance
        user_id: User identifier

    Returns:
        List of StoredPlan matching the criteria
    """
    now = datetime.utcnow()

    async with db.async_session() as session:
        result = await session.execute(
            select(AgentPlanRow)
            .where(AgentPlanRow.user_id == user_id)
            .where(AgentPlanRow.status == "active")
            .where(
                (AgentPlanRow.expires_at.is_(None)) | (AgentPlanRow.expires_at > now)
            )
            .order_by(AgentPlanRow.updated_at.desc())
        )
        rows = result.scalars().all()

        plans = []
        for row in rows:
            payload = ExecutionPlanV2Payload.model_validate_json(row.payload_json)
            plans.append(
                StoredPlan(
                    plan_id=row.plan_id,
                    user_id=row.user_id,
                    payload=payload,
                    status=row.status,
                    updated_at=row.updated_at,
                )
            )

        return plans


async def update_step_status(
    db: Database,
    plan_id: str,
    step_id: str,
    status: str,
    tx_hash: Optional[str] = None,
    receipt: Optional[dict] = None,
    error: Optional[str] = None,
) -> Optional[StoredPlan]:
    """Update a step's status within a plan and return the updated StoredPlan.

    Args:
        db: Database instance
        plan_id: Plan identifier
        step_id: Step identifier
        status: New step status
        tx_hash: Optional transaction hash
        receipt: Optional transaction receipt
        error: Optional error message

    Returns:
        Updated StoredPlan if found, None otherwise
    """
    async with db.async_session() as session:
        result = await session.execute(
            select(AgentPlanRow).where(AgentPlanRow.plan_id == plan_id)
        )
        row = result.scalar_one_or_none()

        if row is None:
            return None

        payload = ExecutionPlanV2Payload.model_validate_json(row.payload_json)

        # Find and update the step
        step_found = False
        for step in payload.steps:
            if step.step_id == step_id:
                step.status = status
                if tx_hash is not None:
                    step.tx_hash = tx_hash
                if receipt is not None:
                    step.receipt = receipt
                if error is not None:
                    step.error = error
                step_found = True
                break

        if not step_found:
            return None

        now = datetime.utcnow()
        payload_json = payload.model_dump_json()

        await session.execute(
            update(AgentPlanRow)
            .where(AgentPlanRow.plan_id == plan_id)
            .values(
                payload_json=payload_json,
                updated_at=now,
            )
        )
        await session.commit()

        return StoredPlan(
            plan_id=row.plan_id,
            user_id=row.user_id,
            payload=payload,
            status=row.status,
            updated_at=now,
        )
