from src.allocator.composer import PoolCandidate
from src.scoring.rubric import score_pool_candidate, sentinel_block_from_candidate


def test_score_pool_candidate_matches_demo_weighting():
    pool = PoolCandidate(
        project="aave-v3",
        symbol="USDC",
        chain="Arbitrum",
        tvl_usd=1_200_000_000,
        apy=6.2,
        audits=True,
        days_live=720,
        stable=True,
        il_risk="no",
        exposure="single",
    )

    score = score_pool_candidate(pool)

    assert score.safety == 100
    assert score.durability == 90
    assert score.exit == 82
    assert score.confidence == 85
    assert score.weighted == 92
    assert score.risk_level == "low"
    assert score.strategy_fit == "conservative"


def test_sentinel_block_from_candidate_uses_existing_schema():
    pool = PoolCandidate(
        project="unknown-farm",
        symbol="USDC-ETH",
        chain="Ethereum",
        tvl_usd=250_000_000,
        apy=32.0,
        audits=False,
        days_live=200,
        stable=True,
        il_risk="yes",
        exposure="multi",
    )

    block = sentinel_block_from_candidate(pool)

    assert block.risk_level in {"HIGH", "MEDIUM", "LOW"}
    assert block.sentinel == 53
    assert "Unaudited" in block.flags
    assert "IL risk" in block.flags
