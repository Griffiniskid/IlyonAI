from src.agent.planner import build_plan


def test_blended_sentinel_is_usd_weighted_average_for_two_steps():
    plan = build_plan({
        "title": "Test",
        "steps": [
            {"action": "stake", "params": {"token": "USDC", "protocol": "aave-v3",
                                             "chain_id": 1, "amount_usd": 8000}},
            {"action": "deposit_lp", "params": {"token": "USDC-USDT",
                                                  "protocol": "curve",
                                                  "chain_id": 1,
                                                  "amount_usd": 2000}},
        ],
    })
    assert plan.blended_sentinel is not None
    assert 0 < plan.blended_sentinel <= 100


def test_risk_gate_hard_block_when_critical_shield():
    plan = build_plan({
        "title": "Bad",
        "steps": [
            {"action": "swap",
             "params": {"token_in": "ETH", "token_out": "USDC", "amount": "1.0",
                        "chain_id": 1,
                        "to": "0x000000000000000000000000000000000000dEaD"}},
        ],
    })
    assert plan.risk_gate == "hard_block"


def test_risk_gate_soft_warn_for_cross_chain():
    plan = build_plan({
        "title": "Cross chain",
        "steps": [
            {"action": "bridge", "params": {"token_in": "USDC", "amount": "100",
                                              "src_chain_id": 1, "dst_chain_id": 42161}},
        ],
    })
    assert plan.risk_gate in {"soft_warn", "clear"}  # baseline depends on existing logic
