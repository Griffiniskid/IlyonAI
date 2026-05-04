from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpportunitySearchRequest:
    risk_levels: list[str] = field(default_factory=list)
    chains: list[str] = field(default_factory=list)
    product_types: list[str] = field(default_factory=list)
    target_apy: float | None = None
    min_apy: float | None = 0.5
    max_apy: float | None = 500.0
    min_tvl: float = 100_000.0
    ranking_objective: str = "constraint_fit_then_risk_adjusted_return"
    limit: int = 8
    execution_requested: bool = False
    include_experimental: bool = False
    asset_hint: str | None = None

    def __post_init__(self) -> None:
        self.risk_levels = [str(level).upper() for level in self.risk_levels]
        self.chains = [str(chain).lower() for chain in self.chains]
        self.product_types = [str(kind).lower() for kind in self.product_types]


@dataclass
class OpportunityCandidate:
    protocol: str
    chain: str
    symbol: str
    apy: float | None
    tvl_usd: float | None
    risk_level: str
    source_id: str | None = None
    source: str = "DefiLlama"
    product_type: str = "pool"
    protocol_slug: str | None = None
    pool_id: str | None = None
    pool_address: str | None = None
    token_addresses: list[str] = field(default_factory=list)
    apy_base: float | None = None
    apy_reward: float | None = None
    volume_24h_usd: float | None = None
    sentinel_summary: dict[str, Any] = field(default_factory=dict)
    source_urls: dict[str, str] = field(default_factory=dict)
    executable: bool = False
    adapter_id: str | None = None
    unsupported_reason: str | None = None

    def __post_init__(self) -> None:
        self.chain = str(self.chain).lower()
        self.risk_level = str(self.risk_level).upper()
        if self.protocol_slug is None:
            self.protocol_slug = self.protocol.lower().replace(" ", "-")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source": self.source,
            "protocol": self.protocol,
            "protocol_slug": self.protocol_slug,
            "chain": self.chain,
            "product_type": self.product_type,
            "symbol": self.symbol,
            "pool_id": self.pool_id,
            "pool_address": self.pool_address,
            "token_addresses": self.token_addresses,
            "apy": self.apy,
            "apy_base": self.apy_base,
            "apy_reward": self.apy_reward,
            "tvl_usd": self.tvl_usd,
            "volume_24h_usd": self.volume_24h_usd,
            "risk_level": self.risk_level,
            "sentinel_summary": self.sentinel_summary,
            "source_urls": self.source_urls,
            "executable": self.executable,
            "adapter_id": self.adapter_id,
            "unsupported_reason": self.unsupported_reason,
        }


@dataclass
class ExcludedOpportunity:
    candidate: OpportunityCandidate
    reason_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = self.candidate.to_dict()
        data["reason_codes"] = self.reason_codes
        return data


@dataclass
class OpportunitySearchResult:
    primary: list[OpportunityCandidate]
    excluded: list[ExcludedOpportunity] = field(default_factory=list)
    research_trace: list[str] = field(default_factory=list)
