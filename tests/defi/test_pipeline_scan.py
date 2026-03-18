import pytest
from src.defi.pipeline.scan import MarketScanPipeline

SOLANA_FIXTURE = {"chain": "solana", "protocol_slug": "orca", "product_type": "stable_lp"}
CHAIN_MATRIX = ["solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"]
EVM_FIXTURE = {"chain": "base", "protocol_slug": "aave-v3", "product_type": "lending_supply_like"}

def test_market_scan_normalizes_pool_farm_and_lending_candidates():
    pipeline = MarketScanPipeline()

    normalized = pipeline.normalize_candidates(
        pools=[{"project": "orca-dex", "symbol": "SOL-USDC", "apy": 12.5}],
        yields=[{"project": "jito", "symbol": "JTO", "apy": 8.0}],
        markets=[{"protocol": "aave-v3", "symbol": "USDC", "apy_supply": 4.2}],
    )

    assert {item["candidate_kind"] for item in normalized} == {"pool", "yield", "lending_supply"}


def test_market_scan_assigns_shortlist_scores():
    pipeline = MarketScanPipeline()

    normalized = pipeline.normalize_candidates(
        pools=[{"project": "orca-dex", "symbol": "SOL-USDC", "apy": 12.5, "tvlUsd": 2_500_000}],
        yields=[],
        markets=[],
    )

    assert normalized[0]["shortlist_score"] > 0


def test_market_scan_keeps_lending_supply_product_type_for_protocol_shaped_markets():
    pipeline = MarketScanPipeline()

    normalized = pipeline.normalize_candidates(
        pools=[],
        yields=[],
        markets=[{"protocol": "aave-v3", "symbol": "USDC", "apy_supply": 4.2}],
    )

    assert normalized[0]["product_type"] == "lending_supply_like"


@pytest.mark.parametrize("chain", CHAIN_MATRIX)
def test_market_scan_excludes_unsupported_chain_candidates(chain):
    pipeline = MarketScanPipeline()

    normalized = pipeline.normalize_candidates(
        pools=[{"project": "orca-dex", "symbol": "SOL-USDC", "chain": "fantom", "apy": 12.5}],
        yields=[],
        markets=[],
    )

    assert normalized == []

def test_market_scan_accepts_solana_fixture():
    pipeline = MarketScanPipeline()
    normalized = pipeline.normalize_candidates(
        pools=[{"project": SOLANA_FIXTURE["protocol_slug"], "symbol": "SOL-USDC", "chain": SOLANA_FIXTURE["chain"], "apy": 12.5}],
        yields=[],
        markets=[],
    )
    assert len(normalized) == 1
    assert normalized[0]["chain"] == "solana"

def test_market_scan_accepts_evm_fixture():
    pipeline = MarketScanPipeline()
    normalized = pipeline.normalize_candidates(
        pools=[],
        yields=[],
        markets=[{"protocol": EVM_FIXTURE["protocol_slug"], "symbol": "USDC", "chain": EVM_FIXTURE["chain"], "apy_supply": 4.2}],
    )
    assert len(normalized) == 1
    assert normalized[0]["chain"] == "base"

