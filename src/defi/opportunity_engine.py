"""Advanced DeFi opportunity orchestration layer."""

from __future__ import annotations

import asyncio
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.analyzer import TokenAnalyzer
from src.data.defillama import DefiLlamaClient
from src.defi.ai_router import DefiAIRouter
from src.defi.docs_analyzer import ProtocolDocsAnalyzer
from src.defi.evidence import build_confidence_report, build_dependency_edges, parse_age_hours
from src.defi.farm_analyzer import FarmAnalyzer
from src.defi.history_store import DefiHistoryStore
from src.defi.lending_analyzer import LENDING_PROTOCOLS, LendingAnalyzer
from src.defi.pool_analyzer import PoolAnalyzer
from src.defi.risk_engine import DefiRiskEngine, MAJOR_SYMBOLS, STABLE_SYMBOLS
from src.defi.scenario_engine import DefiScenarioEngine
from src.intel.rekt_database import AuditDatabase, RektDatabase


SUPPORTED_TOKEN_CHAINS = {"solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float = 0, upper: float = 100) -> int:
    return int(max(lower, min(upper, round(value))))


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in (value or ""))
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


def _title_case_chain(chain: str) -> str:
    return (chain or "unknown").replace("-", " ").title()


def _symbol_parts(symbol: str) -> List[str]:
    return [part.strip().upper() for part in symbol.replace("-", "/").split("/") if part.strip()]


def _pool_value(pool: Dict[str, Any], snake_key: str, legacy_key: Optional[str] = None, default: Any = None) -> Any:
    if snake_key in pool and pool.get(snake_key) is not None:
        return pool.get(snake_key)
    if legacy_key and legacy_key in pool and pool.get(legacy_key) is not None:
        return pool.get(legacy_key)
    return default


class DefiOpportunityEngine:
    def __init__(
        self,
        pool_analyzer: PoolAnalyzer,
        farm_analyzer: FarmAnalyzer,
        lending_analyzer: LendingAnalyzer,
        llama: DefiLlamaClient,
        rekt_db: Optional[RektDatabase] = None,
        audit_db: Optional[AuditDatabase] = None,
        public_ranking_default: str = "balanced",
    ):
        self.pool_analyzer = pool_analyzer
        self.farm_analyzer = farm_analyzer
        self.lending_analyzer = lending_analyzer
        self.llama = llama
        self.rekt = rekt_db or RektDatabase()
        self.audits = audit_db or AuditDatabase()
        self.history = DefiHistoryStore(self.llama)
        self.docs = ProtocolDocsAnalyzer()
        self.risk = DefiRiskEngine(public_ranking_default=public_ranking_default)
        self.scenarios = DefiScenarioEngine()
        self.ai = DefiAIRouter()
        self.public_ranking_default = public_ranking_default
        self._token_analyzer: Optional[TokenAnalyzer] = None
        self._asset_cache: Dict[str, Dict[str, Any]] = {}

    async def close(self):
        await self.docs.close()
        await self.ai.close()
        if self._token_analyzer:
            await self._token_analyzer.close()

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
        ranking = ranking_profile or self.public_ranking_default
        pools_task = self.pool_analyzer.get_top_pools(chain=chain, min_tvl=min_tvl, min_apy=min_apy, limit=max(limit * 3, 36))
        yields_task = self.farm_analyzer.get_yields(chain=chain, min_apy=min_apy, min_tvl=min_tvl, limit=max(limit * 3, 36))
        lending_task = self.lending_analyzer.get_lending_markets(chain=chain, limit=max(limit * 3, 36))
        protocols_task = self.llama.get_protocols()

        if query:
            matching_protocols_task = self.llama.search_protocols(query, limit=max(limit * 3, 30))
            pools, yields, markets, protocol_catalog, matching_protocols = await asyncio.gather(
                pools_task,
                yields_task,
                lending_task,
                protocols_task,
                matching_protocols_task,
            )
        else:
            pools, yields, markets, protocol_catalog = await asyncio.gather(pools_task, yields_task, lending_task, protocols_task)
            matching_protocols = protocol_catalog[:limit]
        protocol_index = self._build_protocol_index(protocol_catalog)

        opportunities: List[Dict[str, Any]] = []
        for pool in pools:
            opportunities.append(await self._build_pool_or_yield_opportunity(pool, "pool", protocol_index, detail_mode=False, ranking_profile=ranking))
        for opportunity in yields:
            opportunities.append(await self._build_pool_or_yield_opportunity(opportunity, "yield", protocol_index, detail_mode=False, ranking_profile=ranking))
        for market in markets:
            opportunities.append(await self._build_lending_opportunity(market, protocol_index, detail_mode=False, ranking_profile=ranking))

        if query:
            opportunities = [item for item in opportunities if self._matches_query(item, query)]
            pools = [item for item in pools if self._matches_raw_query(item, query)]
            yields = [item for item in yields if self._matches_raw_query(item, query)]
            markets = [item for item in markets if self._matches_raw_query(item, query)]

        ranked = self._sort_opportunities(opportunities, ranking)[:limit]
        conservative = max(ranked, key=lambda item: (item["summary"]["safety_score"], item["summary"]["confidence_score"], item["summary"]["opportunity_score"]), default=None)
        balanced = max(ranked, key=lambda item: (item["summary"]["opportunity_score"], item["summary"]["safety_score"]), default=None)
        aggressive = max(ranked, key=lambda item: (item["summary"]["yield_quality_score"], item["summary"]["opportunity_score"]), default=None)
        protocol_spotlights = self._build_protocol_spotlights(protocol_catalog, ranked, protocol_index, limit)

        summary = {
            "total_pool_tvl": round(sum(_safe_float(item.get("tvlUsd") or item.get("tvl_usd")) for item in pools), 2),
            "avg_pool_apy": round(mean([_safe_float(item.get("apy")) for item in pools]), 2) if pools else 0.0,
            "avg_yield_apy": round(mean([_safe_float(item.get("apy")) for item in yields]), 2) if yields else 0.0,
            "high_risk_pool_count": len([item for item in pools if item.get("risk_level") == "HIGH"]),
            "high_risk_yield_count": len([item for item in yields if item.get("risk_level") == "HIGH"]),
            "stressed_lending_market_count": len([item for item in markets if _safe_float(item.get("combined_risk_score")) >= 60]),
            "avg_opportunity_score": round(mean([item["summary"]["opportunity_score"] for item in ranked]), 1) if ranked else 0.0,
            "avg_safety_score": round(mean([item["summary"]["safety_score"] for item in ranked]), 1) if ranked else 0.0,
            "avg_confidence_score": round(mean([item.get("confidence", {}).get("score", item["summary"]["confidence_score"]) for item in ranked]), 1) if ranked else 0.0,
        }
        market_brief = None
        if include_ai:
            market_brief = await self.ai.build_market_brief(
                {
                    "chain": chain,
                    "query": query,
                    "ranking_profile": ranking,
                    "summary": summary,
                    "top_opportunities": [
                        {
                            "title": item["title"],
                            "kind": item["kind"],
                            "chain": item["chain"],
                            "protocol_name": item["protocol_name"],
                            "summary": item["summary"],
                        }
                        for item in ranked[:5]
                    ],
                }
            )

        return {
            "query": query or None,
            "chain": chain,
            "ranking_profile": ranking,
            "public_ranking_default": self.public_ranking_default,
            "count": {
                "pools": len(pools),
                "yields": len(yields),
                "lending_markets": len(markets),
                "protocols": len(protocol_catalog) if isinstance(protocol_catalog, list) else len(protocol_spotlights),
                "opportunities": len(ranked),
            },
            "summary": summary,
            "highlights": {
                "safest_pool": pools[0] if pools else None,
                "best_sustainable_yield": max(yields, key=lambda y: (_safe_float(y.get("sustainability_ratio")), _safe_float(y.get("apy"))), default=None),
                "lowest_risk_lending_market": min(markets, key=lambda m: _safe_float(m.get("combined_risk_score"), 999), default=None),
                "largest_protocol": max(protocol_spotlights, key=lambda p: _safe_float(p.get("tvl")), default=None),
                "best_conservative": conservative,
                "best_balanced": balanced,
                "best_aggressive": aggressive,
            },
            "top_pools": pools[:limit],
            "top_yields": yields[:limit],
            "top_lending_markets": markets[:limit],
            "top_opportunities": ranked,
            "protocol_spotlights": protocol_spotlights,
            "matching_protocols": matching_protocols[:limit],
            "ai_market_brief": market_brief,
            "methodology": {
                "public_ranking_default": "Balanced risk-adjusted yield with hard safety caps.",
                "opportunity_score": "Balanced mode uses 45% safety, 30% yield quality, 15% exit quality, and 10% confidence.",
                "hard_caps": "Recent critical exploits, low-quality reward tokens, shallow exits, and partial analysis cap scores directly.",
                "confidence_score": "Confidence falls when sources disagree, coverage is partial, or key fields are missing.",
            },
            "data_source": "DefiLlama + internal incident/audit intelligence + optional DeFi AI synthesis",
        }

    async def get_protocol_profile(self, slug: str, include_ai: bool = True, ranking_profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
        ranking = ranking_profile or self.public_ranking_default
        protocol = self._resolve_protocol(slug, await self.llama.get_protocols())
        if not protocol:
            return None
        protocol_slug = protocol.get("slug") or slug
        detail = await self.llama.get_protocol_tvl(protocol_slug)
        pools = await self.pool_analyzer.get_top_pools(protocol=protocol_slug, limit=12, min_tvl=0)
        yields = await self.farm_analyzer.get_yields(limit=20, min_tvl=0, min_apy=0)
        yields = [item for item in yields if str(item.get("project") or "").lower() == protocol_slug.lower()][:8]
        markets = await self.lending_analyzer.get_lending_markets(protocol=protocol_slug, limit=12)
        audits, incidents = await self._fetch_protocol_intel(protocol_slug, protocol.get("name") or protocol_slug)
        docs_url = (LENDING_PROTOCOLS.get(protocol_slug, {}) or {}).get("docs_url")
        docs_profile = await self.docs.analyze(protocol.get("url"), docs_url)
        chain_breakdown = self._extract_chain_breakdown(detail)
        exposure_assets = await self._collect_protocol_assets(pools, yields, markets)
        dependencies = build_dependency_edges("protocol", str(chain_breakdown[0]["chain"]).lower() if chain_breakdown else "unknown", protocol.get("name") or protocol_slug, exposure_assets, docs_profile=docs_profile, incidents=incidents)
        scored = self.risk.score_protocol(protocol, detail, audits, incidents, docs_profile, dependencies, surface_count=len(pools) + len(markets) + len(yields))

        protocol_only_index = self._build_protocol_index([protocol])
        top_opportunities = self._sort_opportunities(
            [
                *(await asyncio.gather(*[self._build_pool_or_yield_opportunity(item, "pool", protocol_only_index, True, ranking) for item in pools[:3]])),
                *(await asyncio.gather(*[self._build_pool_or_yield_opportunity(item, "yield", protocol_only_index, True, ranking) for item in yields[:3]])),
                *(await asyncio.gather(*[self._build_lending_opportunity(item, protocol_only_index, True, ranking) for item in markets[:3]])),
            ],
            ranking,
        )[:6]

        profile = {
            "protocol": protocol_slug,
            "display_name": protocol.get("name") or protocol_slug,
            "slug": protocol_slug,
            "category": protocol.get("category") or (detail.get("category") if isinstance(detail, dict) else None),
            "url": protocol.get("url") or (detail.get("url") if isinstance(detail, dict) else None),
            "logo": protocol.get("logo"),
            "chains": protocol.get("chains") or (detail.get("chains") if isinstance(detail, dict) else []) or [],
            "ranking_profile": ranking,
            "summary": scored["summary"],
            "dimensions": scored["dimensions"],
            "confidence": scored["confidence"],
            "chain_breakdown": chain_breakdown,
            "deployments": self._build_deployments(chain_breakdown),
            "top_markets": markets[:8],
            "top_pools": pools[:8],
            "top_opportunities": top_opportunities,
            "audits": audits[:8],
            "incidents": incidents[:8],
            "evidence": self._protocol_evidence(protocol, docs_profile, audits, incidents, pools, markets),
            "scenarios": self._protocol_scenarios(chain_breakdown, incidents),
            "dependencies": dependencies,
            "assets": exposure_assets[:12],
            "docs_profile": docs_profile,
            "governance": {
                "governance_score": docs_profile.get("governance_score"),
                "has_timelock_mentions": docs_profile.get("has_timelock_mentions"),
                "has_multisig_mentions": docs_profile.get("has_multisig_mentions"),
                "has_admin_mentions": docs_profile.get("has_admin_mentions"),
                "has_governance_mentions": docs_profile.get("has_governance_mentions"),
            },
            "methodology": {
                "protocol_safety": "Protocol safety blends contract safety, incident history, market maturity, governance posture, and dependency inheritance.",
                "public_ranking_default": "Balanced risk-adjusted yield with hard safety caps.",
            },
        }
        profile["ai_analysis"] = await self.ai.build_protocol_analysis(profile) if include_ai else None
        return profile

    async def get_opportunity_profile(self, opportunity_id: str, include_ai: bool = True, ranking_profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
        ranking = ranking_profile or self.public_ranking_default
        kind, raw_id = self._decode_opportunity_id(opportunity_id)
        if not kind or not raw_id:
            return None

        protocol_index = self._build_protocol_index(await self.llama.get_protocols())
        if kind in {"pool", "yield"}:
            pools = await self.llama.get_pools(min_tvl=0, min_apy=0)
            raw = next((item for item in pools if (_pool_value(item, "pool_id", "pool") or "") == raw_id), None)
            if not raw:
                return None
            opportunity = await self._build_pool_or_yield_opportunity(raw, kind, protocol_index, detail_mode=True, ranking_profile=ranking)
            peers = await self.farm_analyzer.get_yields(chain=opportunity["chain"], min_tvl=0, min_apy=0, limit=16)
            opportunity["history"] = self.history.summarize_pool_history(await self.history.get_pool_history(raw_id))
            opportunity["related_opportunities"] = [
                await self._build_pool_or_yield_opportunity(item, "yield" if item.get("sustainability_ratio") is not None else "pool", protocol_index, False, ranking)
                for item in peers
                if str(item.get("project") or "").lower() != opportunity["protocol"].lower()
            ][:6]
            opportunity["safer_alternative"] = self._choose_safer_alternative(opportunity["related_opportunities"], opportunity)
        else:
            markets = await self.lending_analyzer.get_lending_markets(limit=200)
            raw = next((item for item in markets if (item.get("pool_id") or "") == raw_id), None)
            if not raw:
                return None
            opportunity = await self._build_lending_opportunity(raw, protocol_index, detail_mode=True, ranking_profile=ranking)
            raw_chain = raw.get("chain")
            chains: Optional[List[str]] = [raw_chain] if isinstance(raw_chain, str) and raw_chain else None
            opportunity["rate_comparison"] = await self.lending_analyzer.compare_rates(asset=raw.get("symbol", ""), chains=chains)
            opportunity["history"] = None
            opportunity["related_opportunities"] = [
                await self._build_lending_opportunity(item, protocol_index, False, ranking)
                for item in markets
                if item.get("symbol") == raw.get("symbol") and item.get("pool_id") != raw.get("pool_id")
            ][:6]
            opportunity["safer_alternative"] = self._choose_safer_alternative(opportunity["related_opportunities"], opportunity)

        protocol_profile = await self.get_protocol_profile(opportunity["protocol_slug"], include_ai=False, ranking_profile=ranking)
        opportunity["protocol_profile"] = protocol_profile
        opportunity["ai_analysis"] = await self.ai.build_opportunity_analysis(opportunity) if include_ai else None
        return opportunity

    async def compare_lending(
        self,
        asset: str,
        chain: Optional[str] = None,
        protocols: Optional[Sequence[str]] = None,
        mode: str = "supply",
        include_ai: bool = False,
        ranking_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        ranking = ranking_profile or self.public_ranking_default
        protocol_set = {item.lower() for item in (protocols or []) if item}
        markets = await self.lending_analyzer.get_lending_markets(chain=chain, asset=asset, limit=200)
        if protocol_set:
            markets = [item for item in markets if str(item.get("protocol") or "").lower() in protocol_set]
        protocol_index = self._build_protocol_index(await self.llama.get_protocols())
        opportunities = [await self._build_lending_opportunity(item, protocol_index, detail_mode=True, ranking_profile=ranking) for item in markets]
        opportunities = self._sort_opportunities(opportunities, ranking)
        matrix = [
            {
                "opportunity_id": item["id"],
                "protocol": item["protocol_name"],
                "chain": item["chain"],
                "asset": item["symbol"],
                "apy": item["apy"],
                "opportunity_score": item["summary"]["opportunity_score"],
                "safety_score": item["summary"]["safety_score"],
                "yield_quality_score": item["summary"]["yield_quality_score"],
                "exit_quality_score": item["summary"]["exit_quality_score"],
                "confidence_score": item["summary"]["confidence_score"],
                "headline": item["summary"]["headline"],
            }
            for item in opportunities[:12]
        ]
        response = {
            "asset": asset.upper(),
            "chain": chain,
            "mode": mode,
            "ranking_profile": ranking,
            "summary": {
                "markets_compared": len(opportunities),
                "best_balanced": opportunities[0] if opportunities else None,
                "safest": max(opportunities, key=lambda item: item["summary"]["safety_score"], default=None),
                "best_yield": max(opportunities, key=lambda item: item["summary"]["yield_quality_score"], default=None),
                "avoid": min(opportunities, key=lambda item: item["summary"]["opportunity_score"], default=None),
            },
            "matrix": matrix,
            "opportunities": opportunities[:8],
            "methodology": {
                "default": "Balanced risk-adjusted yield with hard safety caps.",
                "compare": "Use compare when the asset and chain are constant and protocol quality is the main variable.",
            },
        }
        if include_ai:
            response["ai_market_brief"] = await self.ai.build_market_brief(response)
        return response

    async def simulate_lp(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.scenarios.simulate_lp(payload)

    async def simulate_lending(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.scenarios.simulate_lending(payload)

    async def analyze_position(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.scenarios.analyze_position(payload)

    async def _build_pool_or_yield_opportunity(
        self,
        item: Dict[str, Any],
        kind: str,
        protocol_index: Dict[str, Dict[str, Any]],
        detail_mode: bool,
        ranking_profile: str,
    ) -> Dict[str, Any]:
        project = str(item.get("project") or "unknown")
        protocol = protocol_index.get(project.lower()) or {}
        protocol_slug = protocol.get("slug") or _slugify(project)
        docs_url = (LENDING_PROTOCOLS.get(protocol_slug, {}) or {}).get("docs_url")
        docs_profile = await self.docs.analyze(protocol.get("url"), docs_url) if detail_mode else {"governance_score": 52}
        audits, incidents = await self._fetch_protocol_intel(protocol_slug, protocol.get("name") or project) if detail_mode else ([], [])
        assets = await self._build_asset_profiles(item, kind, detail_mode)
        dependencies = build_dependency_edges(kind, str(item.get("chain") or "").lower(), protocol.get("name") or project, assets, docs_profile=docs_profile, incidents=incidents)
        history_summary = self.history.summarize_pool_history(await self.history.get_pool_history(_pool_value(item, "pool_id", "pool") or "")) if detail_mode else {"available": False}
        protocol_safety = await self._estimate_protocol_safety(protocol, protocol_slug, docs_profile, audits, incidents)
        scored = self.risk.score_opportunity(kind, item, assets, dependencies, protocol_safety, docs_profile, history_summary, incidents, ranking_profile=ranking_profile)

        opportunity = {
            "id": self._encode_opportunity_id(kind, _pool_value(item, "pool_id", "pool") or item.get("symbol") or project),
            "kind": kind,
            "title": f"{'Farm' if kind == 'yield' else 'Provide'} {item.get('symbol') or 'Unknown'} {'on' if kind == 'yield' else 'liquidity on'} {protocol.get('name') or project}",
            "subtitle": f"{protocol.get('name') or project} on {_title_case_chain(str(item.get('chain') or 'unknown').lower())}",
            "protocol": project,
            "protocol_name": protocol.get("name") or project,
            "protocol_slug": protocol_slug,
            "project": project,
            "symbol": str(item.get("symbol") or "Unknown"),
            "chain": str(item.get("chain") or "unknown").lower(),
            "apy": round(_safe_float(item.get("apy")), 2),
            "tvl_usd": round(_safe_float(item.get("tvl_usd") or item.get("tvlUsd")), 2),
            "tags": self._build_pool_tags(item, kind, scored["summary"]["strategy_fit"]),
            "summary": scored["summary"],
            "dimensions": scored["dimensions"],
            "confidence": scored["confidence"],
            "score_caps": scored["score_caps"],
            "evidence": self._opportunity_evidence(kind, item, protocol, assets, dependencies, docs_profile, history_summary, incidents),
            "scenarios": self.scenarios.build_opportunity_scenarios(kind, item),
            "dependencies": dependencies,
            "assets": assets,
            "deployment": {
                "chain": str(item.get("chain") or "unknown").lower(),
                "protocol_slug": protocol_slug,
                "deployment_key": f"{protocol_slug}:{str(item.get('chain') or 'unknown').lower()}",
            },
            "ranking_profile": ranking_profile,
            "raw": {
                "pool": item.get("pool") or item.get("pool_id"),
                "apy_tier": item.get("apy_tier"),
                "exposure_type": item.get("exposure_type") or item.get("exposure"),
                "sustainability_ratio": item.get("sustainability_ratio"),
                "risk_flags": item.get("risk_flags") or [],
                "url": item.get("url"),
            },
        }
        if detail_mode:
            opportunity["history"] = history_summary
        return opportunity

    async def _build_lending_opportunity(
        self,
        item: Dict[str, Any],
        protocol_index: Dict[str, Dict[str, Any]],
        detail_mode: bool,
        ranking_profile: str,
    ) -> Dict[str, Any]:
        project = str(item.get("protocol") or item.get("project") or "unknown")
        protocol = protocol_index.get(project.lower()) or {}
        protocol_slug = protocol.get("slug") or _slugify(project)
        docs_url = (LENDING_PROTOCOLS.get(protocol_slug, {}) or {}).get("docs_url")
        docs_profile = await self.docs.analyze(protocol.get("url"), docs_url) if detail_mode else {"governance_score": 52, "has_oracle_mentions": True}
        audits, incidents = await self._fetch_protocol_intel(protocol_slug, protocol.get("name") or project) if detail_mode else ([], [])
        assets = await self._build_asset_profiles(item, "lending", detail_mode)
        dependencies = build_dependency_edges("lending", str(item.get("chain") or "").lower(), item.get("protocol_display") or protocol.get("name") or project, assets, docs_profile=docs_profile, incidents=incidents)
        protocol_safety = await self._estimate_protocol_safety(protocol, protocol_slug, docs_profile, audits, incidents)
        scored = self.risk.score_opportunity("lending", item, assets, dependencies, protocol_safety, docs_profile, None, incidents, ranking_profile=ranking_profile)

        opportunity = {
            "id": self._encode_opportunity_id("lending", item.get("pool_id") or item.get("symbol") or project),
            "kind": "lending",
            "title": f"Deploy {item.get('symbol') or 'Unknown'} on {item.get('protocol_display') or protocol.get('name') or project}",
            "subtitle": f"{item.get('protocol_display') or protocol.get('name') or project} on {_title_case_chain(str(item.get('chain') or 'unknown').lower())}",
            "protocol": project,
            "protocol_name": item.get("protocol_display") or protocol.get("name") or project,
            "protocol_slug": protocol_slug,
            "project": project,
            "symbol": str(item.get("symbol") or "Unknown"),
            "chain": str(item.get("chain") or "unknown").lower(),
            "apy": round(max(_safe_float(item.get("apy_supply")), _safe_float(item.get("apy_borrow"))), 2),
            "tvl_usd": round(_safe_float(item.get("tvlUsd") or item.get("tvl_usd")), 2),
            "tags": self._build_lending_tags(item, scored["summary"]["strategy_fit"]),
            "summary": scored["summary"],
            "dimensions": scored["dimensions"],
            "confidence": scored["confidence"],
            "score_caps": scored["score_caps"],
            "evidence": self._opportunity_evidence("lending", item, protocol, assets, dependencies, docs_profile, None, incidents),
            "scenarios": self.scenarios.build_opportunity_scenarios("lending", item),
            "dependencies": dependencies,
            "assets": assets,
            "deployment": {
                "chain": str(item.get("chain") or "unknown").lower(),
                "protocol_slug": protocol_slug,
                "deployment_key": f"{protocol_slug}:{str(item.get('chain') or 'unknown').lower()}",
            },
            "ranking_profile": ranking_profile,
            "raw": {
                "apy_supply": item.get("apy_supply"),
                "apy_borrow": item.get("apy_borrow"),
                "utilization_pct": item.get("utilization_pct"),
                "market_risk": item.get("market_risk"),
                "protocol_risk": item.get("protocol_risk"),
            },
        }
        return opportunity

    async def _collect_protocol_assets(self, pools: Sequence[Dict[str, Any]], yields: Sequence[Dict[str, Any]], markets: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        assets: Dict[str, Dict[str, Any]] = {}
        for item, kind in [*[(pool, "pool") for pool in pools[:3]], *[(yld, "yield") for yld in yields[:3]], *[(market, "lending") for market in markets[:3]]]:
            for asset in await self._build_asset_profiles(item, kind, detail_mode=False):
                key = f"{asset.get('role')}:{asset.get('symbol')}:{asset.get('chain')}"
                assets[key] = asset
        return list(assets.values())

    async def _build_asset_profiles(self, item: Dict[str, Any], kind: str, detail_mode: bool) -> List[Dict[str, Any]]:
        chain = str(item.get("chain") or "unknown").lower()
        underlying = item.get("underlying_tokens") or item.get("underlyingTokens") or []
        reward_tokens = item.get("reward_tokens") or item.get("rewardTokens") or []
        symbol = str(item.get("symbol") or "")
        parts = _symbol_parts(symbol)
        assets: List[Dict[str, Any]] = []

        for index, part in enumerate(parts[:4]):
            address = underlying[index] if index < len(underlying) else None
            role = "collateral" if kind == "lending" else "underlying"
            assets.append(await self._resolve_asset_profile(part, address, chain, role, detail_mode))

        for index, address in enumerate(reward_tokens[:2]):
            reward_symbol = f"REWARD-{index + 1}"
            assets.append(await self._resolve_asset_profile(reward_symbol, address, chain, "reward", detail_mode))

        if not assets and symbol:
            assets.append(await self._resolve_asset_profile(symbol.upper(), None, chain, "asset", False))
        return assets[:6]

    async def _resolve_asset_profile(self, symbol: str, address: Optional[str], chain: str, role: str, detail_mode: bool) -> Dict[str, Any]:
        upper_symbol = (symbol or "Unknown").upper()
        cache_key = f"{chain}:{address or upper_symbol}:{role}:{int(detail_mode)}"
        cached = self._asset_cache.get(cache_key)
        if cached:
            return cached

        score = 62
        thesis = "Heuristic asset quality because no direct token intelligence was available."
        source = "heuristic"
        confidence = 56
        token_analysis = None

        if upper_symbol in STABLE_SYMBOLS:
            score = 92 if upper_symbol in {"USDC", "USDT", "DAI"} else 78
            thesis = "Stablecoin quality is inferred from brand maturity, redemption assumptions, and wrapper risk."
            if upper_symbol not in {"USDC", "USDT", "DAI"}:
                thesis = "Stablecoin quality is discounted because wrapper, bridge, or newer stable risk may matter."
        elif upper_symbol in MAJOR_SYMBOLS:
            score = 88 if upper_symbol in {"ETH", "WETH", "BTC", "WBTC", "SOL"} else 78
            thesis = "Blue-chip asset quality is inferred from liquidity depth and broad market acceptance."
        elif role == "reward":
            score = 44
            confidence = 48
            thesis = "Reward-token quality starts discounted because emissions often create sell pressure and thin exit risk."
        elif upper_symbol.startswith("W") or upper_symbol.startswith("C"):
            score = 58
            thesis = "Wrapped or derivative exposure inherits settlement and redemption risk from the wrapper design."

        if detail_mode and address and chain in SUPPORTED_TOKEN_CHAINS and upper_symbol not in STABLE_SYMBOLS and upper_symbol not in MAJOR_SYMBOLS:
            analysis = await self._get_token_intelligence(address, chain)
            if analysis:
                overall = int(analysis.overall_score)
                score = overall
                confidence = 74
                source = "token-engine"
                token_analysis = {
                    "overall_score": overall,
                    "grade": analysis.grade,
                    "recommendation": analysis.recommendation,
                    "ai_analysis": analysis.ai_analysis,
                }
                thesis = f"Inherited token risk from the existing token engine ({analysis.grade}, {overall}/100)."

        profile = {
            "symbol": upper_symbol,
            "role": role,
            "chain": chain,
            "quality_score": _clamp(score),
            "risk_level": "HIGH" if score < 45 else "MEDIUM" if score < 70 else "LOW",
            "confidence_score": _clamp(confidence),
            "source": source,
            "address": address,
            "thesis": thesis,
            "token_analysis": token_analysis,
        }
        self._asset_cache[cache_key] = profile
        return profile

    async def _get_token_intelligence(self, address: str, chain: str):
        analyzer = await self._ensure_token_analyzer()
        return await analyzer.analyze(address, mode="quick", chain=chain)

    async def _ensure_token_analyzer(self) -> TokenAnalyzer:
        if self._token_analyzer is None:
            self._token_analyzer = TokenAnalyzer()
        return self._token_analyzer

    async def _estimate_protocol_safety(
        self,
        protocol: Dict[str, Any],
        protocol_slug: str,
        docs_profile: Dict[str, Any],
        audits: Sequence[Dict[str, Any]],
        incidents: Sequence[Dict[str, Any]],
    ) -> int:
        tvl = _safe_float(protocol.get("tvl"))
        score = 66
        if tvl > 100_000_000:
            score += 10
        elif tvl < 10_000_000:
            score -= 8
        if audits:
            score += min(12, len(audits) * 3)
        else:
            score -= 10
        if incidents:
            score -= min(20, len(incidents) * 6)
        score += int((docs_profile.get("governance_score") or 50 - 50) * 0.25)
        if protocol_slug in LENDING_PROTOCOLS:
            score += 4
        return _clamp(score)

    async def _fetch_protocol_intel(self, protocol_slug: str, display_name: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        audits = await self.audits.get_audits(protocol=display_name, limit=20)
        if not audits and protocol_slug != display_name.lower():
            audits = await self.audits.get_audits(protocol=protocol_slug, limit=20)
        incidents = await self.rekt.get_incidents(search=display_name, limit=20)
        if not incidents and protocol_slug != display_name.lower():
            incidents = await self.rekt.get_incidents(search=protocol_slug, limit=20)
        return audits, incidents

    def _build_protocol_index(self, protocols: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        index: Dict[str, Dict[str, Any]] = {}
        for protocol in protocols or []:
            slug = str(protocol.get("slug") or protocol.get("project") or protocol.get("name") or "").lower()
            name = str(protocol.get("name") or protocol.get("protocol") or slug).lower()
            if slug:
                index[slug] = protocol
            if name and name not in index:
                index[name] = protocol
        return index

    def _resolve_protocol(self, slug: str, protocols: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        target = slug.lower()
        for protocol in protocols or []:
            if str(protocol.get("slug") or "").lower() == target:
                return protocol
        for protocol in protocols or []:
            hay = " ".join([str(protocol.get("slug") or ""), str(protocol.get("name") or ""), str(protocol.get("symbol") or "")]).lower()
            if target in hay:
                return protocol
        return None

    def _extract_chain_breakdown(self, detail: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(detail, dict):
            return []
        chain_tvls = detail.get("chainTvls") or detail.get("chain_tvls") or {}
        rows: List[Dict[str, Any]] = []
        if isinstance(chain_tvls, dict):
            for chain, value in chain_tvls.items():
                current = value.get("tvl") if isinstance(value, dict) else value
                rows.append({"chain": chain, "tvl_usd": _safe_float(current)})
        elif isinstance(detail.get("chains"), list):
            rows = [{"chain": chain, "tvl_usd": None} for chain in detail.get("chains", [])]
        rows.sort(key=lambda item: _safe_float(item.get("tvl_usd")), reverse=True)
        total = sum(_safe_float(item.get("tvl_usd")) for item in rows)
        for row in rows:
            row["share_pct"] = round((_safe_float(row.get("tvl_usd")) / total) * 100, 2) if total > 0 else None
        return rows[:12]

    def _build_deployments(self, chain_breakdown: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deployments = []
        for item in chain_breakdown:
            chain = str(item.get("chain") or "unknown").lower()
            tvl_usd = item.get("tvl_usd")
            deployments.append(
                {
                    "chain": chain,
                    "display_name": _title_case_chain(chain),
                    "tvl_usd": tvl_usd,
                    "share_pct": item.get("share_pct"),
                    "deployment_key": chain,
                }
            )
        return deployments

    def _opportunity_evidence(
        self,
        kind: str,
        item: Dict[str, Any],
        protocol: Dict[str, Any],
        assets: Sequence[Dict[str, Any]],
        dependencies: Sequence[Dict[str, Any]],
        docs_profile: Optional[Dict[str, Any]],
        history_summary: Optional[Dict[str, Any]],
        incidents: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        docs_profile = docs_profile or {}
        evidence = [
            {
                "key": "tvl",
                "title": "Liquidity depth",
                "summary": f"TVL is ${_safe_float(item.get('tvl_usd') or item.get('tvlUsd')):,.0f}, which drives exit quality.",
                "type": "metric",
                "severity": "low" if _safe_float(item.get("tvl_usd") or item.get("tvlUsd")) >= 10_000_000 else "medium",
                "source": "DefiLlama",
                "url": item.get("url"),
            },
            {
                "key": "assets",
                "title": "Asset inheritance",
                "summary": "; ".join(f"{asset['symbol']} ({asset['role']}) quality {asset['quality_score']}/100" for asset in assets[:3]) or "No asset breakdown available.",
                "type": "inheritance",
                "severity": "medium" if any(asset.get("quality_score", 100) < 55 for asset in assets) else "low",
                "source": "token-engine" if any(asset.get("source") == "token-engine" for asset in assets) else "heuristic",
                "url": None,
            },
            {
                "key": "dependencies",
                "title": "Dependency chain",
                "summary": "; ".join(f"{dep['dependency_type']}: {dep['name']}" for dep in dependencies[:3]) or "No explicit dependencies recorded.",
                "type": "dependency",
                "severity": "high" if any(dep.get("risk_score", 0) > 55 for dep in dependencies) else "medium",
                "source": "internal",
                "url": None,
            },
        ]
        if kind != "lending" and item.get("sustainability_ratio") is not None:
            ratio = _safe_float(item.get("sustainability_ratio"))
            evidence.append(
                {
                    "key": "yield-composition",
                    "title": "Yield composition",
                    "summary": f"About {ratio * 100:.0f}% of displayed APY appears fee-backed rather than incentive-backed.",
                    "type": "metric",
                    "severity": "low" if ratio >= 0.5 else "high",
                    "source": "DefiLlama+internal",
                    "url": None,
                }
            )
        if kind == "lending":
            evidence.append(
                {
                    "key": "reserve-health",
                    "title": "Reserve health",
                    "summary": f"Supply APY {item.get('apy_supply', 0):.2f}% vs borrow APY {item.get('apy_borrow', 0):.2f}% at utilization {item.get('utilization_pct', 0):.1f}%.",
                    "type": "metric",
                    "severity": "high" if _safe_float(item.get("utilization_pct")) > 85 else "medium",
                    "source": "DefiLlama",
                    "url": None,
                }
            )
        if history_summary and history_summary.get("available"):
            evidence.append(
                {
                    "key": "history",
                    "title": "History snapshot",
                    "summary": f"30d APY delta {history_summary.get('apy_delta_30d', 0):.1f}% and 30d TVL delta {history_summary.get('tvl_delta_30d', 0):.1f}%.",
                    "type": "history",
                    "severity": "high" if abs(_safe_float(history_summary.get("apy_delta_30d"))) > 100 else "low",
                    "source": "DefiLlama",
                    "url": None,
                }
            )
        if docs_profile.get("available"):
            evidence.append(
                {
                    "key": "docs",
                    "title": "Docs and governance signals",
                    "summary": f"Docs observability {docs_profile.get('observability_score', 0)}/100 with governance score {docs_profile.get('governance_score', 0)}/100.",
                    "type": "docs",
                    "severity": "low" if docs_profile.get("governance_score", 0) >= 60 else "medium",
                    "source": "scraper",
                    "url": docs_profile.get("url"),
                }
            )
        if incidents:
            evidence.append(
                {
                    "key": "incidents",
                    "title": "Incident history",
                    "summary": f"Found {len(incidents)} related incident record(s) for the protocol or brand surface.",
                    "type": "intel",
                    "severity": "high",
                    "source": "RektDatabase",
                    "url": incidents[0].get("post_mortem_url"),
                }
            )
        if protocol:
            evidence.append(
                {
                    "key": "protocol-meta",
                    "title": "Protocol metadata",
                    "summary": f"Protocol TVL is ${_safe_float(protocol.get('tvl')):,.0f} across {len(protocol.get('chains') or [])} chains.",
                    "type": "metadata",
                    "severity": "low",
                    "source": "DefiLlama",
                    "url": protocol.get("url"),
                }
            )
        return evidence[:8]

    def _protocol_evidence(
        self,
        protocol: Dict[str, Any],
        docs_profile: Dict[str, Any],
        audits: Sequence[Dict[str, Any]],
        incidents: Sequence[Dict[str, Any]],
        pools: Sequence[Dict[str, Any]],
        markets: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        evidence = [
            {
                "key": "battle-testing",
                "title": "Battle-testing proxy",
                "summary": f"Protocol TVL is ${_safe_float(protocol.get('tvl')):,.0f} across {len(protocol.get('chains') or [])} chains.",
                "type": "metric",
                "severity": "low" if _safe_float(protocol.get("tvl")) > 100_000_000 else "medium",
                "source": "DefiLlama",
                "url": protocol.get("url"),
            },
            {
                "key": "docs",
                "title": "Docs observability",
                "summary": f"Docs observability {docs_profile.get('observability_score', 0)}/100 and governance score {docs_profile.get('governance_score', 0)}/100.",
                "type": "docs",
                "severity": "low" if docs_profile.get("available") else "medium",
                "source": "scraper",
                "url": docs_profile.get("url"),
            },
            {
                "key": "surface-coverage",
                "title": "Surface coverage",
                "summary": f"Coverage includes {len(pools)} pool-like opportunities and {len(markets)} lending markets in current datasets.",
                "type": "coverage",
                "severity": "low",
                "source": "internal",
                "url": None,
            },
        ]
        if audits:
            evidence.append(
                {
                    "key": "audits",
                    "title": "Audit coverage",
                    "summary": f"Found {len(audits)} audit record(s). Latest known auditor: {audits[0].get('auditor', 'Unknown')}.",
                    "type": "intel",
                    "severity": "low",
                    "source": "AuditDatabase",
                    "url": audits[0].get("report_url"),
                }
            )
        else:
            evidence.append(
                {
                    "key": "audits",
                    "title": "Audit coverage",
                    "summary": "No linked audit records were found in the current internal dataset.",
                    "type": "intel",
                    "severity": "high",
                    "source": "AuditDatabase",
                    "url": None,
                }
            )
        if incidents:
            evidence.append(
                {
                    "key": "incidents",
                    "title": "Incident history",
                    "summary": f"Found {len(incidents)} incident record(s) tied to this protocol or brand surface.",
                    "type": "intel",
                    "severity": "high",
                    "source": "RektDatabase",
                    "url": incidents[0].get("post_mortem_url"),
                }
            )
        return evidence[:8]

    def _protocol_scenarios(self, chain_breakdown: Sequence[Dict[str, Any]], incidents: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scenarios = [
            {
                "key": "governance_or_admin_action",
                "title": "Emergency governance/admin action",
                "impact": "Core markets can reprice quickly if admin controls or governance interventions are activated under stress.",
                "severity": "medium",
                "trigger": "Emergency proposal, pause event, or parameter hotfix lands.",
            },
            {
                "key": "deployment_fragmentation",
                "title": "Deployment fragmentation",
                "impact": "Risk profile can diverge by chain; weak deployments can hurt brand confidence even if the flagship deployment stays healthy.",
                "severity": "medium",
                "trigger": f"Liquidity starts concentrating into only {len(chain_breakdown[:1]) or 1} deployment(s).",
            },
        ]
        if incidents:
            scenarios.append(
                {
                    "key": "recurring_security_theme",
                    "title": "Recurring exploit theme",
                    "impact": "Historical incidents can become relevant again if a similar dependency or governance weakness reappears.",
                    "severity": "high",
                    "trigger": "A new patch cycle, dependency swap, or unusual market behavior resembles prior incident patterns.",
                }
            )
        return scenarios

    def _build_protocol_spotlights(
        self,
        protocol_catalog: Sequence[Dict[str, Any]],
        top_opportunities: Sequence[Dict[str, Any]],
        protocol_index: Dict[str, Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict[str, Any]] = {}
        for opportunity in top_opportunities:
            slug = opportunity.get("protocol_slug") or opportunity.get("protocol")
            if not slug:
                continue
            protocol = protocol_index.get(str(slug).lower()) or {}
            candidate = {
                "slug": slug,
                "name": opportunity.get("protocol_name") or protocol.get("name") or slug,
                "category": protocol.get("category") or "DeFi",
                "tvl": _safe_float(protocol.get("tvl")),
                "chains": protocol.get("chains") or [opportunity.get("chain")],
                "best_opportunity_score": opportunity.get("summary", {}).get("opportunity_score", 0),
                "best_safety_score": opportunity.get("summary", {}).get("safety_score", 0),
                "url": protocol.get("url"),
                "logo": protocol.get("logo"),
            }
            existing = seen.get(str(slug))
            if not existing or candidate["best_opportunity_score"] > existing["best_opportunity_score"]:
                seen[str(slug)] = candidate
        if not seen:
            base = []
            for protocol in protocol_catalog[:limit]:
                base.append(
                    {
                        "slug": protocol.get("slug") or _slugify(protocol.get("name") or "protocol"),
                        "name": protocol.get("name") or "Unknown",
                        "category": protocol.get("category") or "DeFi",
                        "tvl": _safe_float(protocol.get("tvl")),
                        "chains": protocol.get("chains") or [],
                        "best_opportunity_score": 0,
                        "best_safety_score": 0,
                        "url": protocol.get("url"),
                        "logo": protocol.get("logo"),
                    }
                )
            return sorted(base, key=lambda item: item["tvl"], reverse=True)[:limit]
        return sorted(seen.values(), key=lambda item: (item["best_opportunity_score"], item["tvl"]), reverse=True)[:limit]

    def _build_pool_tags(self, item: Dict[str, Any], kind: str, strategy_fit: str) -> List[str]:
        tags = [kind, strategy_fit]
        exposure = item.get("exposure_type") or item.get("exposure")
        if exposure:
            tags.append(str(exposure))
        if str(item.get("il_risk") or item.get("ilRisk") or "").lower() == "yes":
            tags.append("il-risk")
        if _safe_float(item.get("sustainability_ratio"), 1.0) < 0.25:
            tags.append("emissions-heavy")
        return tags[:5]

    def _build_lending_tags(self, item: Dict[str, Any], strategy_fit: str) -> List[str]:
        tags = ["lending", strategy_fit]
        if _safe_float(item.get("utilization_pct")) > 85:
            tags.append("utilization-stress")
        if _safe_float(item.get("apy_borrow")) > 20:
            tags.append("borrow-stress")
        if item.get("audit_status") == "audited":
            tags.append("audited")
        return tags[:5]

    def _sort_opportunities(self, opportunities: Sequence[Dict[str, Any]], ranking: str) -> List[Dict[str, Any]]:
        if ranking == "conservative":
            key_fn = lambda item: (item["summary"]["safety_score"], item["summary"]["confidence_score"], item["summary"]["opportunity_score"])
        else:
            key_fn = lambda item: (item["summary"]["opportunity_score"], item["summary"]["safety_score"], item["summary"]["confidence_score"])
        return sorted(opportunities, key=key_fn, reverse=True)

    def _matches_query(self, opportunity: Dict[str, Any], query: str) -> bool:
        target = query.lower().strip()
        hay = " ".join(
            [
                str(opportunity.get("title") or ""),
                str(opportunity.get("subtitle") or ""),
                str(opportunity.get("protocol") or ""),
                str(opportunity.get("protocol_name") or ""),
                str(opportunity.get("symbol") or ""),
                " ".join(str(asset.get("symbol") or "") for asset in opportunity.get("assets") or []),
            ]
        ).lower()
        return target in hay

    def _matches_raw_query(self, item: Dict[str, Any], query: str) -> bool:
        target = query.lower().strip()
        hay = " ".join([str(item.get("project") or ""), str(item.get("protocol") or ""), str(item.get("symbol") or ""), str(item.get("chain") or "")]).lower()
        return target in hay

    def _choose_safer_alternative(self, related: Sequence[Dict[str, Any]], current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidates = [item for item in related if item["summary"]["safety_score"] > current["summary"]["safety_score"]]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (item["summary"]["safety_score"], item["summary"]["opportunity_score"]), reverse=True)[0]

    def _decode_opportunity_id(self, opportunity_id: str) -> Tuple[Optional[str], Optional[str]]:
        if opportunity_id.startswith("pool--"):
            return "pool", opportunity_id[len("pool--"):]
        if opportunity_id.startswith("yield--"):
            return "yield", opportunity_id[len("yield--"):]
        if opportunity_id.startswith("lending--"):
            return "lending", opportunity_id[len("lending--"):]
        return None, None

    def _encode_opportunity_id(self, kind: str, raw_id: str) -> str:
        return f"{kind}--{raw_id}"
