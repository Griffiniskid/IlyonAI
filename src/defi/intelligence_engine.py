"""Facade for the advanced DeFi opportunity engine."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from src.data.defillama import DefiLlamaClient
from src.defi.farm_analyzer import FarmAnalyzer
from src.defi.lending_analyzer import LendingAnalyzer
from src.defi.opportunity_engine import DefiOpportunityEngine
from src.defi.pool_analyzer import PoolAnalyzer
from src.intel.rekt_database import AuditDatabase, RektDatabase


class DefiIntelligenceEngine:
    def __init__(
        self,
        pool_analyzer: PoolAnalyzer,
        farm_analyzer: FarmAnalyzer,
        lending_analyzer: LendingAnalyzer,
        llama: Optional[DefiLlamaClient] = None,
        rekt_db: Optional[RektDatabase] = None,
        audit_db: Optional[AuditDatabase] = None,
        public_ranking_default: str = "balanced",
    ):
        self.pool_analyzer = pool_analyzer
        self.farm_analyzer = farm_analyzer
        self.lending_analyzer = lending_analyzer
        self.llama = llama or DefiLlamaClient()
        self.rekt = rekt_db or RektDatabase()
        self.audits = audit_db or AuditDatabase()
        self.engine = DefiOpportunityEngine(
            pool_analyzer=self.pool_analyzer,
            farm_analyzer=self.farm_analyzer,
            lending_analyzer=self.lending_analyzer,
            llama=self.llama,
            rekt_db=self.rekt,
            audit_db=self.audits,
            public_ranking_default=public_ranking_default,
        )

    async def close(self):
        await self.engine.close()
        await self.rekt.close()
        await self.audits.close()

    async def analyze_market(
        self,
        chain: Optional[str] = None,
        query: Optional[str] = None,
        min_tvl: float = 100_000,
        min_apy: float = 3.0,
        limit: int = 12,
        include_ai: bool = True,
        ranking_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.engine.analyze_market(
            chain=chain,
            query=query,
            min_tvl=min_tvl,
            min_apy=min_apy,
            limit=limit,
            include_ai=include_ai,
            ranking_profile=ranking_profile,
        )

    async def get_protocol_profile(self, slug: str, include_ai: bool = True, ranking_profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return await self.engine.get_protocol_profile(slug, include_ai=include_ai, ranking_profile=ranking_profile)

    async def get_opportunity_profile(self, opportunity_id: str, include_ai: bool = True, ranking_profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return await self.engine.get_opportunity_profile(opportunity_id, include_ai=include_ai, ranking_profile=ranking_profile)

    async def compare_lending(
        self,
        asset: str,
        chain: Optional[str] = None,
        protocols: Optional[Sequence[str]] = None,
        mode: str = "supply",
        include_ai: bool = False,
        ranking_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.engine.compare_lending(
            asset=asset,
            chain=chain,
            protocols=protocols,
            mode=mode,
            include_ai=include_ai,
            ranking_profile=ranking_profile,
        )

    async def simulate_lp(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.engine.simulate_lp(payload)

    async def simulate_lending(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.engine.simulate_lending(payload)

    async def analyze_position(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.engine.analyze_position(payload)
