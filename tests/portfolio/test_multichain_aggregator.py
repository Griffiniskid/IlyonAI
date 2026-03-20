from src.config import settings
from src.portfolio.multichain_aggregator import CAPABILITIES, MultiChainPortfolioAggregator


def test_aggregator_returns_required_chains_with_capability_matrix():
    aggregator = MultiChainPortfolioAggregator(position_providers=[])
    snapshot = aggregator.aggregate([])

    assert set(snapshot["chains"].keys()) == set(settings.portfolio_required_chains)
    assert set(snapshot["capabilities"]) == set(CAPABILITIES)

    for chain in settings.portfolio_required_chains:
        chain_row = snapshot["chains"][chain]
        assert set(chain_row) == set(CAPABILITIES)
        for capability in CAPABILITIES:
            cell = chain_row[capability]
            assert set(cell) == {"state", "reason"}
            assert cell["state"] == "degraded"
            assert cell["reason"]


def test_degraded_capability_includes_reason():
    class DegradedProvider:
        def capability_overrides(self):
            return {
                "solana": {
                    "lp_positions": {
                        "supported": False,
                        "reason": "provider offline",
                    }
                }
            }

    aggregator = MultiChainPortfolioAggregator(position_providers=[DegradedProvider()])
    snapshot = aggregator.aggregate([])

    degraded_cell = snapshot["chains"]["solana"]["lp_positions"]
    assert degraded_cell["state"] == "degraded"
    assert degraded_cell["reason"] == "provider offline"


def test_provider_must_explicitly_assert_capability_as_available():
    class SpotProvider:
        def capability_overrides(self):
            return {
                "solana": {
                    "spot_holdings": {
                        "supported": True,
                        "reason": None,
                    }
                }
            }

    aggregator = MultiChainPortfolioAggregator(position_providers=[SpotProvider()])
    snapshot = aggregator.aggregate([])

    assert snapshot["chains"]["solana"]["spot_holdings"]["state"] == "available"
    assert snapshot["chains"]["solana"]["lp_positions"]["state"] == "degraded"


def test_override_without_supported_flag_remains_degraded():
    class AmbiguousProvider:
        def capability_overrides(self):
            return {
                "solana": {
                    "risk_decomposition": {
                        "reason": "provider emitted incomplete override",
                    }
                }
            }

    aggregator = MultiChainPortfolioAggregator(position_providers=[AmbiguousProvider()])
    snapshot = aggregator.aggregate([])

    cell = snapshot["chains"]["solana"]["risk_decomposition"]
    assert cell["state"] == "degraded"
    assert cell["reason"] == "provider emitted incomplete override"
