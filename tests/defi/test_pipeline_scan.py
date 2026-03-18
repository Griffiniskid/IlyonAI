from src.defi.pipeline.scan import MarketScanPipeline


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
