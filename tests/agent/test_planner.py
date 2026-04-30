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
    assert plan.blended_sentinel is not None
    assert plan.blended_sentinel >= 65


def test_swap_then_deposit_lp_has_three_steps_and_lp_score():
    plan = build_plan(
        {
            "title": "Swap ETH to USDC then deposit LP",
            "steps": [
                {"step_id": "swap", "action": "swap", "params": {"token_in": "ETH", "token_out": "USDC", "amount": "0.5", "chain_id": 1}},
                {"step_id": "lp", "action": "deposit_lp", "params": {"token": "USDC/USDT", "protocol": "curve", "chain_id": 1}},
            ],
        }
    )

    assert [step.action for step in plan.steps] == ["swap", "approve", "deposit_lp"]
    assert plan.steps[-1].sentinel is not None
    assert plan.steps[-1].sentinel.sentinel >= 65


def test_large_native_stake_requires_double_confirm():
    plan = build_plan(
        {
            "title": "Stake 50 ETH on Lido",
            "steps": [{"step_id": "stake", "action": "stake", "params": {"token": "ETH", "amount": "50", "protocol": "lido", "chain_id": 1, "amount_usd": 150_000}}],
        }
    )

    assert [step.action for step in plan.steps] == ["stake"]
    assert plan.risk_gate == "soft_warn"
    assert plan.requires_double_confirm is True


def test_malicious_swap_is_hard_blocked():
    plan = build_plan(
        {
            "title": "Swap to malicious token",
            "steps": [{"step_id": "swap", "action": "swap", "params": {"token_in": "ETH", "token_out": "KNOWN-MALICIOUS-ADDRESS", "chain_id": 1}}],
        }
    )

    assert plan.risk_gate == "hard_block"
    assert plan.requires_signature_count == 0
    assert any("Known malicious" in warning for warning in plan.risk_warnings)


def test_planner_caps_at_four_explicit_steps():
    plan = build_plan(
        {
            "title": "Too many steps",
            "steps": [
                {"step_id": "a", "action": "transfer", "params": {"token": "USDC", "chain_id": 1}},
                {"step_id": "b", "action": "transfer", "params": {"token": "USDC", "chain_id": 1}},
                {"step_id": "c", "action": "transfer", "params": {"token": "USDC", "chain_id": 1}},
                {"step_id": "d", "action": "transfer", "params": {"token": "USDC", "chain_id": 1}},
                {"step_id": "e", "action": "transfer", "params": {"token": "USDC", "chain_id": 1}},
            ],
        }
    )

    explicit = [step for step in plan.steps if step.action != "approve"]
    assert [step.step_id for step in explicit] == ["a", "b", "c", "d"]
    assert any("capped at 4" in warning for warning in plan.risk_warnings)
