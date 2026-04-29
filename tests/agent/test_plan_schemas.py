from src.api.schemas.agent import ExecutionPlanV2Payload, PlanStepV2


def test_execution_plan_v2_payload_validates_steps():
    step = PlanStepV2(
        step_id="step-1",
        order=1,
        action="bridge",
        params={"token_in": "USDC", "src_chain_id": 1, "dst_chain_id": 42161},
        status="ready",
    )
    plan = ExecutionPlanV2Payload(
        plan_id="plan-1",
        title="Bridge USDC to Arbitrum",
        steps=[step],
        total_steps=1,
        total_gas_usd=8.0,
        total_duration_estimate_s=90,
        blended_sentinel=None,
        requires_signature_count=1,
        risk_warnings=[],
    )

    assert plan.steps[0].action == "bridge"
    assert plan.risk_gate == "clear"
