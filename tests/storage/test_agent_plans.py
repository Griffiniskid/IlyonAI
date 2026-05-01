"""Tests for agent_plans storage layer."""
import pytest
import uuid
from datetime import datetime, timedelta
from src.storage.agent_plans import save_plan, load_plan, list_active_plans, update_step_status, StoredPlan
from src.storage.database import get_database
from src.api.schemas.agent import ExecutionPlanV2Payload, PlanStepV2


def _make_plan(plan_id: str | None = None) -> ExecutionPlanV2Payload:
    """Create a minimal ExecutionPlanV2Payload for testing."""
    return ExecutionPlanV2Payload(
        plan_id=plan_id or f"test-plan-{uuid.uuid4().hex[:8]}",
        title="Test Plan",
        steps=[
            PlanStepV2(
                step_id="step-1",
                order=1,
                action="swap",
                params={"from": "USDC", "to": "SOL", "amount": "100"},
                depends_on=[],
                resolves_from={},
                status="pending",
            ),
            PlanStepV2(
                step_id="step-2",
                order=2,
                action="transfer",
                params={"to": "0xabc", "amount": "50"},
                depends_on=["step-1"],
                resolves_from={"amount": "step-1"},
                status="pending",
            ),
        ],
        total_steps=2,
        total_gas_usd=5.5,
        total_duration_estimate_s=120,
        blended_sentinel=85,
        requires_signature_count=1,
        risk_warnings=[],
        risk_gate="clear",
        requires_double_confirm=False,
        chains_touched=["sol"],
        user_assets_required={"USDC": "100"},
    )


@pytest.mark.asyncio
async def test_save_plan_returns_stored_plan():
    """save_plan must persist and return a StoredPlan with plan_id, user_id, payload, status, updated_at."""
    db = await get_database()
    plan = _make_plan()
    
    stored = await save_plan(
        db,
        user_id=42,
        payload=plan,
        status="active",
        expires_at=None,
    )
    
    assert stored.plan_id is not None
    assert stored.user_id == 42
    assert stored.payload == plan
    assert stored.status == "active"
    assert stored.updated_at is not None


@pytest.mark.asyncio
async def test_load_plan_returns_stored_plan():
    """load_plan must retrieve a previously saved plan by plan_id."""
    db = await get_database()
    plan = _make_plan()
    
    stored = await save_plan(
        db,
        user_id=43,
        payload=plan,
        status="active",
        expires_at=None,
    )
    
    loaded = await load_plan(db, stored.plan_id)
    
    assert loaded is not None
    assert loaded.plan_id == stored.plan_id
    assert loaded.user_id == 43
    assert loaded.payload.plan_id == plan.plan_id
    assert loaded.status == "active"


@pytest.mark.asyncio
async def test_load_plan_returns_none_for_missing():
    """load_plan must return None for a non-existent plan_id."""
    db = await get_database()
    
    loaded = await load_plan(db, "non-existent-plan")
    
    assert loaded is None


@pytest.mark.asyncio
async def test_list_active_plans_returns_user_plans():
    """list_active_plans must return active plans for a specific user only."""
    db = await get_database()
    user_a = 999990
    user_b = 999989
    
    plan_a = _make_plan(plan_id=f"plan-a-{uuid.uuid4().hex[:8]}")
    plan_b = _make_plan(plan_id=f"plan-b-{uuid.uuid4().hex[:8]}")
    
    await save_plan(db, user_id=user_a, payload=plan_a, status="active")
    await save_plan(db, user_id=user_b, payload=plan_b, status="active")
    
    plans = await list_active_plans(db, user_id=user_a)
    
    assert len(plans) == 1
    assert plans[0].payload.plan_id == plan_a.plan_id
    assert plans[0].user_id == user_a


@pytest.mark.asyncio
async def test_list_active_plans_excludes_non_active():
    """list_active_plans must not return plans with non-active status."""
    db = await get_database()
    user_id = 999988
    
    plan_active = _make_plan(plan_id=f"plan-active-{uuid.uuid4().hex[:8]}")
    plan_complete = _make_plan(plan_id=f"plan-complete-{uuid.uuid4().hex[:8]}")
    
    await save_plan(db, user_id=user_id, payload=plan_active, status="active")
    await save_plan(db, user_id=user_id, payload=plan_complete, status="complete")
    
    plans = await list_active_plans(db, user_id=user_id)
    
    assert len(plans) == 1
    assert plans[0].payload.plan_id == plan_active.plan_id


@pytest.mark.asyncio
async def test_list_active_plans_excludes_expired():
    """list_active_plans must not return plans past their expires_at."""
    db = await get_database()
    user_id = 999987
    
    plan_not_expired = _make_plan(plan_id=f"plan-not-expired-{uuid.uuid4().hex[:8]}")
    plan_expired = _make_plan(plan_id=f"plan-expired-{uuid.uuid4().hex[:8]}")
    
    await save_plan(
        db,
        user_id=user_id,
        payload=plan_not_expired,
        status="active",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    await save_plan(
        db,
        user_id=user_id,
        payload=plan_expired,
        status="active",
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    
    plans = await list_active_plans(db, user_id=user_id)
    
    assert len(plans) == 1
    assert plans[0].payload.plan_id == plan_not_expired.plan_id


@pytest.mark.asyncio
async def test_update_step_status_updates_step_and_returns_plan():
    """update_step_status must update the specified step's status, tx_hash, receipt, error, and return updated StoredPlan."""
    db = await get_database()
    plan = _make_plan()
    
    stored = await save_plan(db, user_id=44, payload=plan, status="active")
    
    updated = await update_step_status(
        db,
        plan_id=stored.plan_id,
        step_id="step-1",
        status="confirmed",
        tx_hash="0xabc123",
        receipt={"status": "ok"},
        error=None,
    )
    
    assert updated is not None
    assert updated.plan_id == stored.plan_id
    step = next(s for s in updated.payload.steps if s.step_id == "step-1")
    assert step.status == "confirmed"
    assert step.tx_hash == "0xabc123"
    assert step.receipt == {"status": "ok"}
    assert step.error is None


@pytest.mark.asyncio
async def test_update_step_status_returns_none_for_missing_plan():
    """update_step_status must return None for a non-existent plan_id."""
    db = await get_database()
    
    updated = await update_step_status(
        db,
        plan_id="non-existent-plan",
        step_id="step-1",
        status="confirmed",
        tx_hash=None,
        receipt=None,
        error=None,
    )
    
    assert updated is None


@pytest.mark.asyncio
async def test_update_step_status_returns_none_for_missing_step():
    """update_step_status must return None when step_id not found in plan."""
    db = await get_database()
    plan = _make_plan()
    
    stored = await save_plan(db, user_id=45, payload=plan, status="active")
    
    updated = await update_step_status(
        db,
        plan_id=stored.plan_id,
        step_id="non-existent-step",
        status="confirmed",
        tx_hash=None,
        receipt=None,
        error=None,
    )
    
    assert updated is None
