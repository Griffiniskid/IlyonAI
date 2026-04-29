from src.agent.planner import build_plan


def test_bridge_then_stake_injects_wait_receipt_and_soft_warns():
    plan = build_plan(
        {
            "title": "Bridge USDC to Arbitrum and stake on Aave",
            "steps": [
                {
                    "step_id": "step-1",
                    "action": "bridge",
                    "params": {
                        "token_in": "USDC",
                        "amount": "1000000000",
                        "src_chain_id": 1,
                        "dst_chain_id": 42161,
                    },
                },
                {
                    "step_id": "step-2",
                    "action": "stake",
                    "params": {"token": "USDC", "protocol": "aave-v3", "chain_id": 42161},
                    "resolves_from": {"amount": "step-1.received_amount"},
                },
            ],
        }
    )

    assert [step.action for step in plan.steps] == ["approve", "bridge", "wait_receipt", "stake"]
    assert plan.steps[1].step_id == "step-1"
    assert plan.steps[3].depends_on == [plan.steps[2].step_id]
    assert plan.risk_gate == "soft_warn"
    assert plan.requires_double_confirm is True
