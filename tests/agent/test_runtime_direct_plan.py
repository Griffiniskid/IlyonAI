from src.agent.runtime import _compose_plan_from_message


def test_compose_plan_from_message_detects_bridge_then_stake():
    plan = _compose_plan_from_message("bridge 1000 USDC from Ethereum to Arbitrum and stake it on Aave")

    assert plan is not None
    assert [step.action for step in plan.steps] == ["approve", "bridge", "wait_receipt", "stake"]
    assert plan.risk_gate == "soft_warn"
