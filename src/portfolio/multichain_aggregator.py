from __future__ import annotations

from typing import Any

from src.config import settings

CAPABILITIES = [
    "spot_holdings",
    "lp_positions",
    "lending_positions",
    "vault_positions",
    "risk_decomposition",
    "alert_coverage",
]

DEFAULT_DEGRADED_REASON = "capability coverage unknown - provider did not assert support"


def _default_cell() -> dict[str, Any]:
    return {"state": "degraded", "reason": DEFAULT_DEGRADED_REASON}


def _default_chain_row() -> dict[str, dict[str, Any]]:
    return {capability: _default_cell() for capability in CAPABILITIES}


class MultiChainPortfolioAggregator:
    def __init__(self, position_providers: list[Any] | None = None):
        self.position_providers = position_providers or []

    def aggregate(self, positions: list[dict]) -> dict[str, Any]:
        del positions

        chains = {chain: _default_chain_row() for chain in settings.portfolio_required_chains}

        for provider in self.position_providers:
            override_map = getattr(provider, "capability_overrides", None)
            if not callable(override_map):
                continue
            provider_overrides = override_map()
            if not isinstance(provider_overrides, dict):
                continue
            for chain, capability_map in provider_overrides.items():
                if chain not in chains:
                    continue
                if not isinstance(capability_map, dict):
                    continue
                for capability, config in capability_map.items():
                    if capability not in chains[chain]:
                        continue
                    if not isinstance(config, dict):
                        continue
                    supported = config.get("supported")
                    reason = config.get("reason")
                    chains[chain][capability] = {
                        "state": "available" if supported is True else "degraded",
                        "reason": None if supported is True else (reason or DEFAULT_DEGRADED_REASON),
                    }

        return {
            "chains": chains,
            "capabilities": CAPABILITIES,
        }
