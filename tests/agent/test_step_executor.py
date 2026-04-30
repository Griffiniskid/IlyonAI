from src.agent.planner import build_plan
from src.agent.step_executor import PlanExecutionStore, StepExecutor


def test_step_executor_unlocks_next_step_after_receipt_confirmation():
    plan = build_plan(
        {
            "title": "Bridge and stake",
            "steps": [
                {"step_id": "bridge", "action": "bridge", "params": {"token_in": "USDC", "amount": "1000000", "src_chain_id": 1, "dst_chain_id": 42161}},
                {"step_id": "stake", "action": "stake", "params": {"token": "USDC", "protocol": "aave-v3", "chain_id": 42161}},
            ],
        }
    )
    store = PlanExecutionStore()
    executor = StepExecutor(store)
    executor.save_plan(user_id=1, plan=plan)

    first = plan.steps[0]
    frames = executor.mark_broadcast(plan.plan_id, first.step_id, "0xaaa")
    frames += executor.confirm_step(plan.plan_id, first.step_id, {"status": "0x1"})

    assert frames[-1].event == "step_status"
    loaded = store.load(plan.plan_id)
    assert loaded is not None
    assert loaded.payload.steps[0].status == "confirmed"
    assert loaded.payload.steps[1].status == "ready"


def test_step_executor_aborts_plan_without_unlocking_followups():
    plan = build_plan(
        {
            "title": "Bridge and stake",
            "steps": [
                {"step_id": "bridge", "action": "bridge", "params": {"token_in": "USDC", "amount": "1000000", "src_chain_id": 1, "dst_chain_id": 42161}},
                {"step_id": "stake", "action": "stake", "params": {"token": "USDC", "protocol": "aave-v3", "chain_id": 42161}},
            ],
        }
    )
    executor = StepExecutor(PlanExecutionStore())
    executor.save_plan(user_id=1, plan=plan)

    frames = executor.abort_plan(plan.plan_id, "user rejected signing")

    assert frames[-1].event == "plan_complete"
    assert frames[-1].payload["status"] == "aborted"
