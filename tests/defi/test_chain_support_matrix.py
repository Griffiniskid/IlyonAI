from src.defi.farm_analyzer import FarmAnalyzer
from src.defi.lending_analyzer import LendingAnalyzer
from src.defi.opportunity_taxonomy import PHASE_1_CHAINS
from src.defi.pipeline.scan import MarketScanPipeline
from src.defi.pool_analyzer import PoolAnalyzer


def test_phase1_chain_support_matrix_is_consistent():
    assert PoolAnalyzer.SUPPORTED_CHAINS == PHASE_1_CHAINS
    assert FarmAnalyzer.SUPPORTED_CHAINS == PHASE_1_CHAINS
    assert LendingAnalyzer.SUPPORTED_CHAINS == PHASE_1_CHAINS
    assert MarketScanPipeline.SUPPORTED_CHAINS == PHASE_1_CHAINS
