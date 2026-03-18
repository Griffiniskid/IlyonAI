from src.defi.scoring.deterministic import DeterministicScorer


def test_reward_heavy_profiles_take_larger_apr_haircuts_than_fee_backed_profiles():
    scorer = DeterministicScorer()
    reward_heavy = scorer.score(
        kind="yield",
        candidate={"product_type": "incentivized_crypto_crypto_lp", "apy": 60.0, "apy_base": 8.0, "apy_reward": 52.0, "tvl_usd": 1_500_000},
        context={"protocol_safety": 68, "behavior": {}, "history": {}, "docs": {}},
    )
    fee_backed = scorer.score(
        kind="pool",
        candidate={"product_type": "stable_lp", "apy": 12.0, "apy_base": 11.0, "apy_reward": 1.0, "tvl_usd": 1_500_000},
        context={"protocol_safety": 68, "behavior": {}, "history": {}, "docs": {}},
    )

    reward_haircut = reward_heavy["summary"]["gross_apr"] - reward_heavy["summary"]["haircut_apr"]
    fee_haircut = fee_backed["summary"]["gross_apr"] - fee_backed["summary"]["haircut_apr"]
    assert reward_haircut > fee_haircut
