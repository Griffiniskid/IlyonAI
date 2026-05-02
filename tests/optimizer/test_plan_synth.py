from src.optimizer.plan_synth import build_rebalance_intent


def test_build_rebalance_intent_returns_steps():
    intent = build_rebalance_intent([
        {"to": {"token": "USDC", "protocol": "aave-v3", "chain_id": 42161, "usd": 1000, "apy": 5.0}},
    ])
    assert intent["steps"][0]["action"] == "stake"
    assert intent["steps"][0]["params"]["protocol"] == "aave-v3"
