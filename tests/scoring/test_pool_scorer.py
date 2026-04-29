from src.scoring.normalizer import pool_candidate_from_mapping
from src.scoring.pool_scorer import score_pool_mapping


def test_normalizes_defillama_pool_fields():
    pool = pool_candidate_from_mapping(
        {
            "project": "aave-v3",
            "symbol": "USDC",
            "chain": "Arbitrum",
            "tvlUsd": 850_000_000,
            "apy": 4.8,
            "stablecoin": True,
            "ilRisk": "no",
        }
    )

    assert pool.project == "aave-v3"
    assert pool.symbol == "USDC"
    assert pool.chain == "Arbitrum"
    assert pool.tvl_usd == 850_000_000
    assert pool.audits is True
    assert pool.stable is True
    assert pool.exposure == "single"


def test_score_pool_mapping_returns_existing_sentinel_block():
    block = score_pool_mapping(
        {
            "project": "unknown",
            "symbol": "USDC-ETH",
            "chain": "Ethereum",
            "tvlUsd": 300_000_000,
            "apy": 18.0,
            "stablecoin": False,
            "ilRisk": "yes",
        }
    )

    assert block.sentinel < 82
    assert block.risk_level in {"HIGH", "MEDIUM"}
    assert "Unaudited" in block.flags
