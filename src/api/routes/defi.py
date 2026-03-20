"""
DeFi API routes: pools, yields, lending, and protocol analysis.

GET /api/v1/defi/pools                   - Top liquidity pools with risk scoring
GET /api/v1/defi/pools/{pool_id}         - Single pool detail + history
GET /api/v1/defi/yields                  - Yield farming opportunities
GET /api/v1/defi/lending                 - Lending markets across protocols
GET /api/v1/defi/lending/{protocol}      - Specific lending protocol overview
GET /api/v1/defi/lending/rates/{asset}   - Compare rates for an asset across protocols
GET /api/v1/defi/health                  - Calculate position health factor
GET /api/v1/defi/protocols               - Top DeFi protocols by TVL
GET /api/v1/defi/protocol/{slug}         - Protocol detail
"""

import asyncio
import logging
from typing import Dict, Optional

from aiohttp import web

from src.api.schemas.requests import AnalyzePoolRequest
from src.chains.base import ChainType
from src.chains.registry import ChainRegistry
from src.config import settings
from src.data.dexscreener import DexScreenerClient
from src.defi.opportunity_taxonomy import classify_defi_record
from src.defi.pool_analyzer import PoolAnalyzer
from src.defi.farm_analyzer import FarmAnalyzer
from src.defi.lending_analyzer import LendingAnalyzer
from src.defi.intelligence_engine import DefiIntelligenceEngine
from src.data.defillama import DefiLlamaClient
from src.api.response_envelope import envelope_error_response, envelope_response

logger = logging.getLogger(__name__)

_pool_analyzer: Optional[PoolAnalyzer] = None
_farm_analyzer: Optional[FarmAnalyzer] = None
_lending_analyzer: Optional[LendingAnalyzer] = None
_llama: Optional[DefiLlamaClient] = None
_intelligence_engine: Optional[DefiIntelligenceEngine] = None
_pair_client: Optional[DexScreenerClient] = None


def _pool_tvl(item: dict) -> float:
    return float(item.get("tvl_usd") or item.get("tvlUsd") or 0)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _infer_pool_kind(pool: dict) -> str:
    taxonomy = classify_defi_record(pool)
    return str(taxonomy.get("default_kind") or "pool")


def _pair_project_slug(pair: dict) -> str:
    dex = str(pair.get("dexId") or "unknown").strip().lower()
    labels = {str(label).strip().lower() for label in pair.get("labels") or []}
    if dex == "uniswap":
        if "v4" in labels:
            return "uniswap-v4"
        if "v3" in labels:
            return "uniswap-v3"
        return "uniswap-v2"
    if dex == "pancakeswap":
        return "pancakeswap-amm"
    if dex == "curve":
        return "curve-dex"
    if dex == "orca":
        return "orca-dex"
    if dex == "raydium":
        return "raydium-amm"
    return dex or "unknown"


def _ordered_pair_symbols(pair: dict) -> list[str]:
    stable_symbols = {"USDC", "USDT", "DAI", "FDUSD", "USDE", "BUSD", "TUSD", "FRAX", "LUSD"}
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    base_symbol = str(base.get("symbol") or "").upper()
    quote_symbol = str(quote.get("symbol") or "").upper()
    if quote_symbol in stable_symbols and base_symbol not in stable_symbols:
        return [quote_symbol, base_symbol]
    return [base_symbol, quote_symbol]


def _chain_type_from_value(value: Optional[str]) -> Optional[ChainType]:
    if not value:
        return None
    try:
        return ChainType(str(value).strip().lower())
    except Exception:
        return None


async def _fetch_pool_fee_tier_pct(chain_value: str, pair_address: str) -> Optional[float]:
    chain_type = _chain_type_from_value(chain_value)
    if not chain_type or not chain_type.is_evm or len(pair_address) != 42:
        return None

    registry = ChainRegistry.get_instance()
    registry.initialize(settings)
    client = registry.get_client(chain_type)
    eth_call = getattr(client, "_eth_call", None)
    if eth_call is None:
        return None
    raw = await eth_call(pair_address, "0xddca3f43")
    if not raw or raw == "0x":
        return None
    try:
        fee_units = int(raw, 16)
    except Exception:
        return None
    if fee_units <= 0:
        return None
    return round(fee_units / 10000.0, 4)


def _estimate_pair_apy(pair: dict, fee_tier_pct: Optional[float]) -> float:
    if not fee_tier_pct:
        return 0.0
    volume_1d = _safe_float((pair.get("volume") or {}).get("h24"))
    liquidity = _safe_float((pair.get("liquidity") or {}).get("usd"))
    if volume_1d <= 0 or liquidity <= 0:
        return 0.0
    daily_fees = volume_1d * (fee_tier_pct / 100.0)
    return round((daily_fees * 365.0 / liquidity) * 100.0, 4)


async def _build_direct_pair_item(pair_address: str, chain_value: str, pair: dict) -> Dict[str, object]:
    fee_tier_pct = await _fetch_pool_fee_tier_pct(chain_value, pair_address)
    estimated_apy = _estimate_pair_apy(pair, fee_tier_pct)
    symbols = [symbol for symbol in _ordered_pair_symbols(pair) if symbol]
    stable_count = sum(1 for symbol in symbols if symbol in {"USDC", "USDT", "DAI", "FDUSD", "USDE", "BUSD", "TUSD", "FRAX", "LUSD"})
    symbol = "-".join(symbols) if symbols else "UNKNOWN-UNKNOWN"
    label_suffix = " ".join(str(label).upper() for label in pair.get("labels") or [])
    pool_meta = f"{fee_tier_pct:.2f}% {label_suffix}".strip() if fee_tier_pct else f"Direct pair {label_suffix}".strip()
    item = {
        "pool_id": pair_address,
        "pool": pair_address,
        "pair_address": pair_address,
        "project": _pair_project_slug(pair),
        "symbol": symbol,
        "chain": str(pair.get("chainId") or chain_value or "").upper(),
        "tvl_usd": _safe_float((pair.get("liquidity") or {}).get("usd")),
        "tvlUsd": _safe_float((pair.get("liquidity") or {}).get("usd")),
        "apy": estimated_apy,
        "apy_base": estimated_apy,
        "apyBase": estimated_apy,
        "apy_reward": 0.0,
        "apyReward": 0.0,
        "volume_usd_1d": _safe_float((pair.get("volume") or {}).get("h24")),
        "volumeUsd1d": _safe_float((pair.get("volume") or {}).get("h24")),
        "stablecoin": stable_count >= 1,
        "exposure": "multi",
        "il_risk": "no" if stable_count >= 2 else "yes",
        "ilRisk": "no" if stable_count >= 2 else "yes",
        "underlying_tokens": [
            (pair.get("baseToken") or {}).get("address"),
            (pair.get("quoteToken") or {}).get("address"),
        ],
        "underlyingTokens": [
            (pair.get("baseToken") or {}).get("address"),
            (pair.get("quoteToken") or {}).get("address"),
        ],
        "reward_tokens": [],
        "rewardTokens": [],
        "pool_meta": pool_meta,
        "poolMeta": pool_meta,
        "url": pair.get("url") or "",
        "direct_pair": True,
        "source": "dexpair",
    }
    item.update(classify_defi_record(item))
    return item


async def _analyze_direct_pair(req: AnalyzePoolRequest) -> Optional[Dict[str, object]]:
    if _intelligence_engine is None or _pair_client is None or _llama is None:
        return None

    pair_address = str(req.pair_address or req.pool_id or "").strip()
    pair = await _pair_client.find_pair(pair_address, chain=req.chain)
    if not pair:
        return None

    item = await _build_direct_pair_item(pair_address, str(pair.get("chainId") or req.chain or ""), pair)
    protocol_index = _intelligence_engine.engine._build_protocol_index(await _llama.get_protocols())
    opportunity = await _intelligence_engine.engine._build_pool_or_yield_opportunity(
        item,
        "pool",
        protocol_index,
        detail_mode=True,
        ranking_profile=req.ranking_profile,
    )
    opportunity["history"] = {"available": False, "points": []}
    opportunity["related_opportunities"] = []
    opportunity["safer_alternative"] = None
    opportunity["raw"] = {
        **opportunity.get("raw", {}),
        "pair_address": pair_address,
        "source": "dexpair",
        "pool_url": pair.get("url"),
    }
    opportunity["protocol_profile"] = await _intelligence_engine.get_protocol_profile(
        opportunity["protocol_slug"],
        include_ai=False,
        ranking_profile=req.ranking_profile,
    )
    opportunity["ai_analysis"] = await _intelligence_engine.engine.ai.build_opportunity_analysis(opportunity) if req.include_ai else None
    return opportunity


def _build_defi_highlights(pools: list, yields: list, markets: list, protocols: list) -> dict:
    safest_pool = next((p for p in pools if p.get("risk_level") == "LOW"), pools[0] if pools else None)
    sustainable_yield = max(
        yields,
        key=lambda y: ((y.get("sustainability_ratio") or 0), (y.get("apy") or 0)),
        default=None,
    )
    lowest_risk_market = min(markets, key=lambda m: m.get("combined_risk_score") or 999, default=None)
    largest_protocol = max(protocols, key=lambda p: p.get("tvl") or 0, default=None)

    return {
        "safest_pool": safest_pool,
        "best_sustainable_yield": sustainable_yield,
        "lowest_risk_lending_market": lowest_risk_market,
        "largest_protocol": largest_protocol,
    }


async def init_defi(app: web.Application):
    global _pool_analyzer, _farm_analyzer, _lending_analyzer, _llama, _intelligence_engine, _pair_client
    _pool_analyzer = PoolAnalyzer()
    _farm_analyzer = FarmAnalyzer()
    _lending_analyzer = LendingAnalyzer()
    _llama = DefiLlamaClient()
    _pair_client = DexScreenerClient()
    _intelligence_engine = DefiIntelligenceEngine(
        pool_analyzer=_pool_analyzer,
        farm_analyzer=_farm_analyzer,
        lending_analyzer=_lending_analyzer,
        llama=_llama,
    )
    app["defi_pool_analyzer"] = _pool_analyzer
    app["defi_farm_analyzer"] = _farm_analyzer
    app["defi_lending_analyzer"] = _lending_analyzer
    app["defi_llama"] = _llama
    app["defi_intelligence_engine"] = _intelligence_engine
    app["defi_pair_client"] = _pair_client
    logger.info("DeFi analyzers initialized")


async def cleanup_defi(app: web.Application):
    global _pool_analyzer, _farm_analyzer, _lending_analyzer, _llama, _intelligence_engine, _pair_client
    if _pool_analyzer:
        await _pool_analyzer.close()
    if _farm_analyzer:
        await _farm_analyzer.close()
    if _lending_analyzer:
        await _lending_analyzer.close()
    if _llama:
        await _llama.close()
    if _pair_client:
        await _pair_client.close()
    if _intelligence_engine:
        await _intelligence_engine.close()
    logger.info("DeFi analyzers closed")


async def get_pools(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/pools

    Query params:
      chain      - Filter by chain name (ethereum, bsc, polygon, etc.)
      protocol   - Filter by protocol slug (uniswap-v3, aave-v3, etc.)
      min_tvl    - Minimum TVL in USD (default: 100000)
      min_apy    - Minimum APY % (optional)
      max_apy    - Maximum APY % (optional)
      limit      - Max results (default: 50, max: 200)
    """
    if _pool_analyzer is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    q = request.rel_url.query
    chain = q.get("chain")
    protocol = q.get("protocol")
    try:
        min_apy_raw = q.get("min_apy")
        max_apy_raw = q.get("max_apy")
        min_tvl = float(q.get("min_tvl") or "100000")
        limit = min(int(q.get("limit", "50")), 200)
        min_apy = float(min_apy_raw) if min_apy_raw is not None else None
        max_apy = float(max_apy_raw) if max_apy_raw is not None else None
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid numeric query parameter"}, status=400)

    try:
        pools = await _pool_analyzer.get_top_pools(
            chain=chain,
            protocol=protocol,
            min_tvl=min_tvl,
            min_apy=min_apy,
            max_apy=max_apy,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Pool fetch error: {e}")
        return web.json_response({"error": "Failed to fetch pools"}, status=500)

    high_risk = [p for p in pools if p.get("risk_level") == "HIGH"]

    return web.json_response({
        "pools": pools,
        "count": len(pools),
        "filters": {
            "chain": chain,
            "protocol": protocol,
            "min_tvl": min_tvl,
            "min_apy": min_apy,
            "max_apy": max_apy,
        },
        "summary": {
            "high_risk_pools": len(high_risk),
            "total_tvl": sum(_pool_tvl(p) for p in pools),
        },
        "data_source": "DefiLlama",
    })


async def get_pool_detail(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/pools/{pool_id}

    Fetch detailed data + 30-day history for a specific pool.
    """
    if _pool_analyzer is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    pool_id = request.match_info.get("pool_id", "").strip()
    if not pool_id:
        return web.json_response({"error": "pool_id required"}, status=400)

    try:
        detail = await _pool_analyzer.get_pool_detail(pool_id)
    except Exception as e:
        logger.error(f"Pool detail error for {pool_id}: {e}")
        return web.json_response({"error": "Failed to fetch pool detail"}, status=500)

    if not detail:
        return web.json_response({"error": f"Pool {pool_id} not found"}, status=404)

    return web.json_response(detail)


async def get_yields(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/yields

    Fetch yield farming opportunities, ranked and filtered.

    Query params:
      chain           - Filter by chain
      exposure        - stable-stable | crypto-stable | crypto-crypto
      min_apy         - Minimum APY % (default: 1)
      max_apy         - Maximum APY % (cap extreme farms)
      min_tvl         - Minimum TVL (default: 50000)
      min_sustainability - 0.0-1.0, minimum fraction of APY from fees (not emissions)
      limit           - Max results (default: 50)
    """
    if _farm_analyzer is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    q = request.rel_url.query
    chain = q.get("chain")
    exposure = q.get("exposure")

    try:
        max_apy_raw = q.get("max_apy")
        min_apy = float(q.get("min_apy") or "1")
        min_tvl = float(q.get("min_tvl") or "50000")
        max_apy = float(max_apy_raw) if max_apy_raw is not None else None
        min_sust = float(q.get("min_sustainability") or "0")
        limit = min(int(q.get("limit", "50")), 200)
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid numeric query parameter"}, status=400)

    if exposure and exposure not in ("stable-stable", "crypto-stable", "crypto-crypto"):
        return web.json_response(
            {"error": "exposure must be one of: stable-stable, crypto-stable, crypto-crypto"},
            status=400,
        )

    try:
        yields = await _farm_analyzer.get_yields(
            chain=chain,
            exposure=exposure,
            min_apy=min_apy,
            max_apy=max_apy,
            min_tvl=min_tvl,
            min_sustainability=min_sust,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Yield fetch error: {e}")
        return web.json_response({"error": "Failed to fetch yields"}, status=500)

    return web.json_response({
        "yields": yields,
        "count": len(yields),
        "filters": {
            "chain": chain,
            "exposure": exposure,
            "min_apy": min_apy,
            "max_apy": max_apy,
            "min_tvl": min_tvl,
            "min_sustainability": min_sust,
        },
        "data_source": "DefiLlama",
    })


async def analyze_defi(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/analyze

    Combined DeFi analyzer workflow for pools, yields, lending, and protocols.
    """
    if _intelligence_engine is None:
        return envelope_error_response(
            "DeFi analyzer not available",
            code="SERVICE_UNAVAILABLE",
            http_status=503,
        )

    q = request.rel_url.query
    chain = q.get("chain")
    query = (q.get("query") or q.get("protocol") or q.get("asset") or "").strip()
    include_ai = q.get("include_ai", "true").lower() != "false"
    ranking_profile = (q.get("ranking_profile") or q.get("ranking") or "balanced").strip().lower()

    try:
        min_tvl = float(q.get("min_tvl") or "100000")
        min_apy = float(q.get("min_apy") or "3")
        limit = min(int(q.get("limit") or "10"), 25)
    except (ValueError, TypeError):
        return envelope_error_response(
            "Invalid numeric query parameter",
            code="INVALID_QUERY",
            http_status=400,
        )

    try:
        analysis = await _intelligence_engine.analyze_market(
            chain=chain,
            query=query or None,
            min_tvl=min_tvl,
            min_apy=min_apy,
            limit=limit,
            include_ai=include_ai,
            ranking_profile=ranking_profile,
        )
    except Exception as e:
        logger.error(f"DeFi analyzer error: {e}")
        return envelope_error_response(
            "Failed to analyze DeFi opportunities",
            code="DEFI_ANALYSIS_FAILED",
            http_status=500,
        )

    return envelope_response(analysis)


async def analyze_pool(request: web.Request) -> web.Response:
    """
    POST /api/v1/defi/pool/analyze

    Analyze a single pool by raw DefiLlama pool id and return the full
    opportunity profile used by the new unified pool page.
    """
    if _intelligence_engine is None or _llama is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    try:
        req = AnalyzePoolRequest(**payload)
    except Exception as e:
        return web.json_response({"error": "Invalid request", "details": str(e)}, status=400)

    try:
        if req.source == "dexpair" or req.pair_address:
            detail = await _analyze_direct_pair(req)
            if not detail:
                return web.json_response({"error": f"Pair '{req.pair_address or req.pool_id}' could not be analyzed"}, status=404)
            return web.json_response(detail)

        pools = await _llama.get_pools(min_tvl=0, min_apy=0)
        raw_pool = next(
            (item for item in pools if str(item.get("pool_id") or item.get("pool") or "") == req.pool_id),
            None,
        )
        if not raw_pool:
            return web.json_response({"error": f"Pool '{req.pool_id}' not found"}, status=404)

        taxonomy = classify_defi_record(raw_pool)
        if not taxonomy.get("supports_pool_route"):
            return web.json_response(
                {
                    "error": "This yield product is not a pool-style LP and should not be opened on the pool route.",
                    "product_type": taxonomy.get("product_type"),
                },
                status=400,
            )

        kind = req.kind or str(taxonomy.get("default_kind") or _infer_pool_kind(raw_pool))
        detail = await _intelligence_engine.get_opportunity_profile(
            f"{kind}--{req.pool_id}",
            include_ai=req.include_ai,
            ranking_profile=req.ranking_profile,
        )
    except Exception as e:
        logger.error(f"Pool analysis error for {req.pool_id}: {e}", exc_info=True)
        return web.json_response({"error": "Failed to analyze pool"}, status=500)

    if not detail:
        return web.json_response({"error": f"Pool '{req.pool_id}' could not be analyzed"}, status=404)

    return web.json_response(detail)


async def get_opportunities(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/opportunities

    Return ranked DeFi opportunities with explicit score dimensions,
    evidence, and scenario summaries.
    """
    if _intelligence_engine is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    q = request.rel_url.query
    chain = q.get("chain")
    query = (q.get("query") or q.get("protocol") or q.get("asset") or "").strip()
    include_ai = q.get("include_ai", "false").lower() == "true"
    ranking_profile = (q.get("ranking_profile") or q.get("ranking") or "balanced").strip().lower()

    try:
        min_tvl = float(q.get("min_tvl") or "100000")
        min_apy = float(q.get("min_apy") or "3")
        limit = min(int(q.get("limit", "20")), 40)
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid numeric query parameter"}, status=400)

    try:
        analysis = await _intelligence_engine.analyze_market(
            chain=chain,
            query=query or None,
            min_tvl=min_tvl,
            min_apy=min_apy,
            limit=limit,
            include_ai=include_ai,
            ranking_profile=ranking_profile,
        )
    except Exception as e:
        logger.error(f"Opportunity fetch error: {e}")
        return web.json_response({"error": "Failed to fetch DeFi opportunities"}, status=500)

    return web.json_response({
        "opportunities": analysis.get("top_opportunities", []),
        "count": len(analysis.get("top_opportunities", [])),
        "summary": analysis.get("summary", {}),
        "highlights": analysis.get("highlights", {}),
        "methodology": analysis.get("methodology", {}),
        "filters": {
            "chain": chain,
            "query": query or None,
            "min_tvl": min_tvl,
            "min_apy": min_apy,
            "ranking_profile": ranking_profile,
        },
        "ai_market_brief": analysis.get("ai_market_brief"),
        "data_source": analysis.get("data_source"),
    })


async def get_opportunity_detail(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/opportunities/{opportunity_id}

    Detailed opportunity analysis with dimensions, evidence, history, and
    optional AI explanation.
    """
    if _intelligence_engine is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    opportunity_id = request.match_info.get("opportunity_id", "").strip()
    if not opportunity_id:
        return web.json_response({"error": "opportunity_id required"}, status=400)

    include_ai = request.rel_url.query.get("include_ai", "true").lower() != "false"
    ranking_profile = (request.rel_url.query.get("ranking_profile") or request.rel_url.query.get("ranking") or "balanced").strip().lower()

    try:
        detail = await _intelligence_engine.get_opportunity_profile(opportunity_id, include_ai=include_ai, ranking_profile=ranking_profile)
    except Exception as e:
        logger.error(f"Opportunity detail error for {opportunity_id}: {e}")
        return web.json_response({"error": "Failed to fetch DeFi opportunity"}, status=500)

    if not detail:
        return web.json_response({"error": f"Opportunity '{opportunity_id}' not found"}, status=404)

    return web.json_response(detail)


async def get_protocols(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/protocols

    Top DeFi protocols by TVL.

    Query params:
      chain  - Filter by chain
      limit  - Max results (default: 50)
    """
    if _llama is None:
        return web.json_response({"error": "DeFi data not available"}, status=503)

    q = request.rel_url.query
    chain = q.get("chain")
    try:
        limit = min(int(q.get("limit", "50")), 200)
    except ValueError:
        limit = 50

    try:
        protocols = await _llama.get_protocols()
    except Exception as e:
        logger.error(f"Protocols fetch error: {e}")
        return web.json_response({"error": "Failed to fetch protocols"}, status=500)

    if chain:
        protocols = [
            p for p in protocols
            if chain.lower() in [c.lower() for c in (p.get("chains") or [])]
        ]

    protocols = protocols[:limit]

    return web.json_response({
        "protocols": protocols,
        "count": len(protocols),
        "filter_chain": chain,
        "data_source": "DefiLlama",
    })


async def get_protocol_detail(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/protocol/{slug}

    Detailed TVL + chain breakdown for a specific protocol.
    """
    if _intelligence_engine is None:
        return web.json_response({"error": "DeFi data not available"}, status=503)

    slug = request.match_info.get("slug", "").strip().lower()
    if not slug:
        return web.json_response({"error": "protocol slug required"}, status=400)

    include_ai = request.rel_url.query.get("include_ai", "true").lower() != "false"
    ranking_profile = (request.rel_url.query.get("ranking_profile") or request.rel_url.query.get("ranking") or "balanced").strip().lower()

    try:
        detail = await _intelligence_engine.get_protocol_profile(slug, include_ai=include_ai, ranking_profile=ranking_profile)
    except Exception as e:
        logger.error(f"Protocol detail error for {slug}: {e}")
        return web.json_response({"error": f"Failed to fetch protocol {slug}"}, status=500)

    if not detail:
        return web.json_response({"error": f"Protocol '{slug}' not found"}, status=404)

    return web.json_response(detail)


async def get_lending_markets(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/lending

    Fetch lending markets across Aave, Compound, Morpho, Solend, MarginFi, Kamino, etc.

    Query params:
      protocol  - Filter by protocol slug (aave-v3, compound-v3, morpho, etc.)
      chain     - Filter by chain
      asset     - Filter by asset symbol (USDC, ETH, etc.)
      limit     - Max results (default 50)
    """
    if _lending_analyzer is None:
        return web.json_response({"error": "Lending analyzer not available"}, status=503)

    q = request.rel_url.query
    protocol = q.get("protocol")
    chain = q.get("chain")
    asset = q.get("asset")
    try:
        limit = min(int(q.get("limit", "50")), 200)
    except ValueError:
        limit = 50

    try:
        markets = await _lending_analyzer.get_lending_markets(
            protocol=protocol, chain=chain, asset=asset, limit=limit
        )
    except Exception as e:
        logger.error(f"Lending markets error: {e}")
        return web.json_response({"error": "Failed to fetch lending markets"}, status=500)

    return web.json_response({
        "markets": markets,
        "count": len(markets),
        "filters": {"protocol": protocol, "chain": chain, "asset": asset},
        "data_source": "DefiLlama",
    })


async def get_lending_protocol(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/lending/{protocol}

    Full overview of a single lending protocol (TVL, markets, audit, risk).
    """
    if _lending_analyzer is None:
        return web.json_response({"error": "Lending analyzer not available"}, status=503)

    protocol = request.match_info.get("protocol", "").strip().lower()
    if not protocol:
        return web.json_response({"error": "protocol slug required"}, status=400)

    try:
        overview = await _lending_analyzer.get_protocol_overview(protocol)
    except Exception as e:
        logger.error(f"Lending protocol error for {protocol}: {e}")
        return web.json_response({"error": f"Failed to fetch protocol {protocol}"}, status=500)

    if not overview:
        return web.json_response(
            {"error": f"Protocol '{protocol}' not found. Try: aave-v3, compound-v3, morpho, spark, solend, marginfi, kamino"},
            status=404,
        )

    return web.json_response(overview)


async def compare_lending_rates(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/lending/rates/{asset}

    Compare supply and borrow rates for an asset across all protocols.

    Query params:
      chain - Restrict comparison to a specific chain
    """
    if _lending_analyzer is None:
        return web.json_response({"error": "Lending analyzer not available"}, status=503)

    asset = request.match_info.get("asset", "").strip().upper()
    if not asset:
        return web.json_response({"error": "asset symbol required"}, status=400)

    chain = request.rel_url.query.get("chain")
    chains = [chain] if chain else None

    try:
        comparison = await _lending_analyzer.compare_rates(asset=asset, chains=chains)
    except Exception as e:
        logger.error(f"Rate comparison error for {asset}: {e}")
        return web.json_response({"error": "Failed to compare rates"}, status=500)

    return web.json_response(comparison)


async def calculate_health(request: web.Request) -> web.Response:
    """
    GET /api/v1/defi/health

    Calculate health factor for a lending position.

    Query params:
      collateral_usd  - Collateral value in USD (required)
      debt_usd        - Debt value in USD (required)
      protocol        - Protocol slug for liquidation threshold (default: aave-v3)
      ltv             - Override liquidation threshold 0.0-1.0 (optional)
    """
    if _lending_analyzer is None:
        return web.json_response({"error": "Lending analyzer not available"}, status=503)

    q = request.rel_url.query
    try:
        ltv_raw = q.get("ltv")
        collateral_usd = float(q.get("collateral_usd") or "0")
        debt_usd = float(q.get("debt_usd") or "0")
        ltv = float(ltv_raw) if ltv_raw is not None else None
    except ValueError:
        return web.json_response({"error": "Invalid numeric parameter"}, status=400)

    protocol = q.get("protocol", "aave-v3")

    if collateral_usd < 0 or debt_usd < 0:
        return web.json_response({"error": "collateral_usd and debt_usd must be >= 0"}, status=400)

    result = _lending_analyzer.calculate_health_factor(
        collateral_usd=collateral_usd,
        debt_usd=debt_usd,
        protocol=protocol,
        collateral_ltv=ltv,
    )
    return web.json_response(result)


async def discover_defi_v2(request: web.Request) -> web.Response:
    """GET /api/v2/defi/discover - advanced DeFi discovery surface."""
    return await analyze_defi(request)


async def get_protocol_detail_v2(request: web.Request) -> web.Response:
    """GET /api/v2/defi/protocols/{slug} - entity-first protocol profile."""
    return await get_protocol_detail(request)


async def get_opportunity_detail_v2(request: web.Request) -> web.Response:
    """GET /api/v2/defi/opportunities/{opportunity_id} - entity-first opportunity profile."""
    return await get_opportunity_detail(request)


async def compare_defi_v2(request: web.Request) -> web.Response:
    """GET /api/v2/defi/compare - compare lending opportunities on the same asset surface."""
    if _intelligence_engine is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    q = request.rel_url.query
    asset = (q.get("asset") or "").strip().upper()
    if not asset:
        return web.json_response({"error": "asset required"}, status=400)

    chain = q.get("chain")
    protocols = [item.strip() for item in (q.get("protocols") or "").split(",") if item.strip()]
    mode = (q.get("mode") or "supply").strip().lower()
    include_ai = q.get("include_ai", "false").lower() == "true"
    ranking_profile = (q.get("ranking_profile") or q.get("ranking") or "balanced").strip().lower()

    try:
        comparison = await _intelligence_engine.compare_lending(
            asset=asset,
            chain=chain,
            protocols=protocols or None,
            mode=mode,
            include_ai=include_ai,
            ranking_profile=ranking_profile,
        )
    except Exception as e:
        logger.error(f"DeFi compare error: {e}")
        return web.json_response({"error": "Failed to compare DeFi opportunities"}, status=500)

    return web.json_response(comparison)


async def simulate_lp_v2(request: web.Request) -> web.Response:
    """POST /api/v2/defi/simulate/lp - LP and farm stress simulation."""
    if _intelligence_engine is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    try:
        result = await _intelligence_engine.simulate_lp(payload)
    except Exception as e:
        logger.error(f"LP simulation error: {e}")
        return web.json_response({"error": "Failed to simulate LP position"}, status=500)

    return web.json_response(result)


async def simulate_lending_v2(request: web.Request) -> web.Response:
    """POST /api/v2/defi/simulate/lending - lending stress simulation."""
    if _intelligence_engine is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    try:
        result = await _intelligence_engine.simulate_lending(payload)
    except Exception as e:
        logger.error(f"Lending simulation error: {e}")
        return web.json_response({"error": "Failed to simulate lending position"}, status=500)

    return web.json_response(result)


async def analyze_position_v2(request: web.Request) -> web.Response:
    """POST /api/v2/defi/positions/analyze - position-aware stress analysis."""
    if _intelligence_engine is None:
        return web.json_response({"error": "DeFi analyzer not available"}, status=503)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    try:
        result = await _intelligence_engine.analyze_position(payload)
    except Exception as e:
        logger.error(f"Position analysis error: {e}")
        return web.json_response({"error": "Failed to analyze DeFi position"}, status=500)

    return web.json_response(result)


def setup_defi_routes(app: web.Application):
    """Register DeFi routes and lifecycle hooks."""
    app.on_startup.append(init_defi)
    app.on_cleanup.append(cleanup_defi)

    app.router.add_get("/api/v1/defi/analyze", analyze_defi)
    app.router.add_post("/api/v1/defi/pool/analyze", analyze_pool)
    app.router.add_get("/api/v1/defi/pools", get_pools)
    app.router.add_get("/api/v1/defi/pools/{pool_id}", get_pool_detail)
    app.router.add_get("/api/v1/defi/yields", get_yields)
    app.router.add_get("/api/v1/defi/opportunities/{opportunity_id}", get_opportunity_detail)
    app.router.add_get("/api/v1/defi/opportunities", get_opportunities)
    # Lending routes — order matters: specific paths before parameterized ones
    app.router.add_get("/api/v1/defi/lending/rates/{asset}", compare_lending_rates)
    app.router.add_get("/api/v1/defi/lending/{protocol}", get_lending_protocol)
    app.router.add_get("/api/v1/defi/lending", get_lending_markets)
    app.router.add_get("/api/v1/defi/health", calculate_health)
    app.router.add_get("/api/v1/defi/protocols", get_protocols)
    app.router.add_get("/api/v1/defi/protocol/{slug}", get_protocol_detail)

    app.router.add_get("/api/v2/defi/discover", discover_defi_v2)
    app.router.add_get("/api/v2/defi/protocols/{slug}", get_protocol_detail_v2)
    app.router.add_get("/api/v2/defi/opportunities/{opportunity_id}", get_opportunity_detail_v2)
    app.router.add_get("/api/v2/defi/compare", compare_defi_v2)
    app.router.add_post("/api/v2/defi/simulate/lp", simulate_lp_v2)
    app.router.add_post("/api/v2/defi/simulate/lending", simulate_lending_v2)
    app.router.add_post("/api/v2/defi/positions/analyze", analyze_position_v2)

    logger.info("DeFi routes registered (pools, yields, lending, protocols)")
