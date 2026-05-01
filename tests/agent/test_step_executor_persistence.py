import pytest

from src.agent.step_executor import PlanExecutionStore
from src.api.schemas.agent import ExecutionPlanV2Payload, PlanStepV2
from src.storage.database import get_database


def _plan() -> ExecutionPlanV2Payload:
    return ExecutionPlanV2Payload(
        plan_id="plan-exec-1",
        title="Persist test",
        steps=[PlanStepV2(step_id="s1", order=1, action="bridge", params={})],
        total_steps=1,
        total_gas_usd=5.0,
        total_duration_estimate_s=60,
        blended_sentinel=70,
        requires_signature_count=1,
        risk_warnings=[],
    )


async def _cleanup_plan(db, plan_id: str) -> None:
    from sqlalchemy import delete
    from src.storage.database import AgentPlanRow
    async with db.async_session() as session:
        await session.execute(delete(AgentPlanRow).where(AgentPlanRow.plan_id == plan_id))
        await session.commit()


@pytest.mark.asyncio
async def test_save_and_load_via_store():
    db = await get_database()
    store = PlanExecutionStore(db=db)
    await _cleanup_plan(db, "plan-exec-1")
    saved = await store.save(user_id=1, plan=_plan())
    assert saved.payload.plan_id == "plan-exec-1"

    fetched = await store.load(plan_id="plan-exec-1")
    assert fetched is not None
    assert fetched.payload.title == "Persist test"


@pytest.mark.asyncio
async def test_update_step_round_trip():
    db = await get_database()
    store = PlanExecutionStore(db=db)
    plan = _plan()
    plan.plan_id = "plan-exec-2"
    await _cleanup_plan(db, "plan-exec-2")
    await store.save(user_id=1, plan=plan)
    await store.update_step(plan_id="plan-exec-2", step_id="s1", status="confirmed", tx_hash="0x1")

    fetched = await store.load(plan_id="plan-exec-2")
    assert fetched.payload.steps[0].status == "confirmed"
    assert fetched.payload.steps[0].tx_hash == "0x1"
