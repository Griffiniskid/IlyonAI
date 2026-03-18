from src.defi.pipeline.scan import MarketScanPipeline


def test_provider_normalization_preserves_all_phase1_chains():
    pipeline = MarketScanPipeline()
    chains = {"solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"}

    normalized = {pipeline.normalize_chain_name(chain) for chain in chains}

    assert normalized == chains


def test_provider_normalization_maps_common_aliases_to_phase1_chains():
    pipeline = MarketScanPipeline()

    assert pipeline.normalize_chain_name("eth") == "ethereum"
    assert pipeline.normalize_chain_name("avax") == "avalanche"
    assert pipeline.normalize_chain_name("bnb chain") == "bsc"
