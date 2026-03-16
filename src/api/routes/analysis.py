"""
Token analysis API routes — multi-chain.

Provides endpoints for token analysis across all supported chains.
"""

import logging
import asyncio
import math
import re
from aiohttp import web
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import quote

from src.core.analyzer import TokenAnalyzer
from src.core.models import AnalysisResult, TokenInfo
from src.chains.address import AddressResolver
from src.api.schemas.responses import (
    AnalysisResponse, TokenBasicInfo, ScoresResponse, MarketDataResponse,
    SecurityResponse, HolderAnalysisResponse, AIAnalysisResponse,
    SocialsResponse, WebsiteAnalysisResponse, DeployerForensicsResponse,
    AnomalyDetectionResponse, ErrorResponse
)
from src.api.schemas.requests import AnalyzeTokenRequest, AnalysisModeType
from src.defi.opportunity_taxonomy import classify_defi_record
from src.storage.cache import CacheLayer
from src.storage.database import get_database

logger = logging.getLogger(__name__)

# Global analyzer instance (initialized on app startup)
_analyzer: Optional[TokenAnalyzer] = None
_cache: Optional[CacheLayer] = None
_resolver = AddressResolver()


async def init_analyzer(app: web.Application):
    """Initialize analyzer on app startup"""
    global _analyzer, _cache
    _analyzer = TokenAnalyzer()
    _cache = CacheLayer()
    app['analyzer'] = _analyzer
    app['cache'] = _cache
    logger.info("TokenAnalyzer initialized for web API (multi-chain)")


async def cleanup_analyzer(app: web.Application):
    """Cleanup analyzer on app shutdown"""
    global _analyzer
    if _analyzer:
        await _analyzer.close()
        logger.info("TokenAnalyzer closed")


def _get_explorer_url(address: str, chain: str) -> Optional[str]:
    """Build block explorer URL for a token address."""
    explorers = {
        "solana": f"https://solscan.io/token/{address}",
        "ethereum": f"https://etherscan.io/token/{address}",
        "base": f"https://basescan.org/token/{address}",
        "arbitrum": f"https://arbiscan.io/token/{address}",
        "bsc": f"https://bscscan.com/token/{address}",
        "polygon": f"https://polygonscan.com/token/{address}",
        "optimism": f"https://optimistic.etherscan.io/token/{address}",
        "avalanche": f"https://snowtrace.io/token/{address}",
    }
    return explorers.get(chain)


def _liquidity_lock_status(token: TokenInfo) -> str:
    if token.liquidity_locked is True:
        return "locked"
    if token.liquidity_locked is False:
        return "unlocked"
    return "unknown"


def convert_result_to_response(result: AnalysisResult, mode: str, cached: bool = False) -> dict:
    """Convert AnalysisResult to API response dict"""
    token = result.token
    chain = token.chain

    return AnalysisResponse(
        chain=chain,
        token=TokenBasicInfo(
            address=token.address,
            name=token.name,
            symbol=token.symbol,
            decimals=token.decimals,
            logo_url=token.logo_url,
            chain=chain,
            chain_id=token.chain_id,
            explorer_url=_get_explorer_url(token.address, chain),
        ),
        scores=ScoresResponse(
            overall=result.overall_score,
            grade=result.grade,
            safety=result.safety_score,
            liquidity=result.liquidity_score,
            distribution=result.distribution_score,
            social=result.social_score,
            activity=result.activity_score,
            honeypot=result.honeypot_score,
            deployer=result.deployer_reputation_score,
            anomaly=result.behavioral_anomaly_score
        ),
        market=MarketDataResponse(
            price_usd=token.price_usd,
            market_cap=token.market_cap,
            fdv=token.fdv,
            liquidity_usd=token.liquidity_usd,
            volume_24h=token.volume_24h,
            volume_1h=token.volume_1h,
            price_change_24h=token.price_change_24h,
            price_change_6h=token.price_change_6h,
            price_change_1h=token.price_change_1h,
            price_change_5m=token.price_change_5m,
            buys_24h=token.buys_24h,
            sells_24h=token.sells_24h,
            txns_24h=token.txns_24h,
            age_hours=token.age_hours,
            dex_name=token.dex_name,
            pair_address=token.pair_address
        ),
        security=SecurityResponse(
            mint_authority_enabled=token.mint_authority_enabled,
            freeze_authority_enabled=token.freeze_authority_enabled,
            liquidity_locked=token.liquidity_locked,
            lp_lock_percent=token.lp_lock_percent,
            liquidity_lock_status=_liquidity_lock_status(token),
            liquidity_lock_source=token.liquidity_lock_source,
            liquidity_lock_note=token.liquidity_lock_note,
            honeypot_status=token.honeypot_status,
            honeypot_is_honeypot=token.honeypot_is_honeypot,
            honeypot_sell_tax_percent=token.honeypot_sell_tax_percent,
            honeypot_explanation=token.honeypot_explanation,
            honeypot_warnings=token.honeypot_warnings,
            can_mint=token.can_mint,
            can_blacklist=token.can_blacklist,
            can_pause=token.can_pause,
            is_upgradeable=token.is_upgradeable,
            is_renounced=token.is_renounced,
            is_proxy_contract=token.is_proxy_contract,
            is_verified=token.is_verified,
            buy_tax=token.goplus_buy_tax,
            sell_tax=token.goplus_sell_tax,
            transfer_pausable=token.transfer_pausable,
            is_open_source=token.is_open_source,
        ),
        holders=HolderAnalysisResponse(
            top_holder_pct=token.top_holder_pct,
            holder_concentration=token.holder_concentration,
            suspicious_wallets=token.suspicious_wallets,
            dev_wallet_risk=token.dev_wallet_risk,
            holder_flags=token.holder_flags,
            top_holders=token.top_holders[:10]
        ),
        ai=AIAnalysisResponse(
            available=token.ai_available,
            verdict=token.ai_verdict,
            score=token.ai_score,
            confidence=token.ai_confidence,
            rug_probability=token.ai_rug_probability,
            summary=token.ai_summary,
            recommendation=token.ai_recommendation,
            red_flags=token.ai_red_flags,
            green_flags=token.ai_green_flags,
            code_audit=token.ai_code_audit,
            whale_risk=token.ai_whale_risk,
            sentiment=token.ai_sentiment,
            trading=token.ai_trading,
            narrative=token.ai_narrative,
            grok=token.grok_analysis
        ),
        socials=SocialsResponse(
            has_twitter=token.has_twitter,
            has_website=token.has_website,
            has_telegram=token.has_telegram,
            twitter_url=token.twitter_url,
            website_url=token.website_url,
            telegram_url=token.telegram_url,
            socials_count=token.socials_count
        ),
        website=WebsiteAnalysisResponse(
            quality=token.website_quality,
            is_legitimate=token.website_is_legitimate,
            has_privacy_policy=token.website_has_privacy_policy,
            has_terms=token.website_has_terms,
            has_copyright=token.website_has_copyright,
            has_contact=token.website_has_contact,
            has_tokenomics=token.website_has_tokenomics,
            has_roadmap=token.website_has_roadmap,
            has_team=token.website_has_team,
            has_whitepaper=token.website_has_whitepaper,
            has_audit=token.website_has_audit,
            audit_provider=token.website_audit_provider,
            red_flags=token.website_red_flags,
            ai_quality=token.website_ai_quality,
            ai_concerns=token.website_ai_concerns
        ),
        deployer=DeployerForensicsResponse(
            available=token.deployer_forensics_available,
            address=token.deployer_address,
            reputation_score=token.deployer_reputation_score,
            risk_level=token.deployer_risk_level,
            tokens_deployed=token.deployer_tokens_deployed,
            rugged_tokens=token.deployer_rugged_tokens,
            rug_percentage=token.deployer_rug_percentage,
            is_known_scammer=token.deployer_is_known_scammer,
            patterns_detected=token.deployer_patterns_detected,
            evidence_summary=token.deployer_evidence_summary
        ),
        anomaly=AnomalyDetectionResponse(
            available=token.anomaly_available,
            score=token.anomaly_score,
            rug_probability=token.anomaly_rug_probability,
            time_to_rug=token.anomaly_time_to_rug,
            severity=token.anomaly_severity,
            anomalies_detected=token.anomalies_detected,
            recommendation=token.anomaly_recommendation,
            confidence=token.anomaly_confidence
        ),
        recommendation=result.recommendation,
        analyzed_at=datetime.utcnow(),
        analysis_mode=mode,
        cached=cached
    ).model_dump(mode='json')


def _search_text(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _address_candidates_from_query(query: str) -> List[str]:
    text = str(query or "").strip()
    if not text:
        return []
    candidates: List[str] = []
    direct = re.fullmatch(r"0x[a-fA-F0-9]{40,64}", text)
    if direct:
        return [text]
    for match in re.finditer(r"0x[a-fA-F0-9]{40,64}", text):
        value = match.group(0)
        if value not in candidates:
            candidates.append(value)
    return candidates


def _pool_search_score(pool: dict, query_lower: str) -> float:
    pool_id = _search_text(pool.get("pool_id") or pool.get("pool"))
    symbol = _search_text(pool.get("symbol"))
    project = _search_text(pool.get("project"))
    chain = _search_text(pool.get("chain"))
    subtitle = " ".join(part for part in [symbol, project, chain] if part)

    base = 0.0
    if query_lower == pool_id:
        base = 180.0
    elif query_lower == symbol:
        base = 130.0
    elif query_lower == project:
        base = 120.0
    elif query_lower in f"{project} {symbol}" and query_lower in project and query_lower in symbol:
        base = 114.0
    elif query_lower in symbol:
        base = 108.0
    elif query_lower in project:
        base = 102.0
    elif query_lower in subtitle:
        base = 88.0

    if base <= 0:
        return -1.0

    tvl = float(pool.get("tvl_usd") or pool.get("tvlUsd") or 0)
    apy = float(pool.get("apy") or 0)
    tvl_bonus = min(18.0, 4.0 * math.log10(max(tvl, 1.0)))
    apy_bonus = min(max(apy, 0.0), 40.0) * 0.12
    return base + tvl_bonus + apy_bonus


def _pair_project_aliases(pair: dict) -> List[str]:
    dex = _search_text(pair.get("dexId"))
    labels = {_search_text(label) for label in pair.get("labels") or []}
    aliases = {dex}
    if dex == "uniswap":
        if "v4" in labels:
            aliases.add("uniswap-v4")
        if "v3" in labels:
            aliases.add("uniswap-v3")
        if "v2" in labels:
            aliases.add("uniswap-v2")
    elif dex == "curve":
        aliases.add("curve-dex")
    elif dex == "raydium":
        aliases.update({"raydium-amm", "raydium-clmm"})
    elif dex == "orca":
        aliases.add("orca-dex")
    elif dex == "aerodrome":
        aliases.update({"aerodrome-slipstream", "aerodrome"})
    elif dex == "pancakeswap":
        aliases.update({"pancakeswap-amm-v3", "pancakeswap-amm"})
    elif dex == "shadow":
        aliases.update({"shadow-exchange", "shadow-exchange-clmm"})
    return [alias for alias in aliases if alias]


def _resolve_pool_from_pair(pair: dict, raw_pools: List[dict]) -> Optional[Tuple[dict, dict, float]]:
    pair_chain = _search_text(pair.get("chainId"))
    project_aliases = set(_pair_project_aliases(pair))
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    pair_addresses = {
        _search_text(base.get("address")),
        _search_text(quote.get("address")),
    } - {""}
    pair_symbols = {
        _search_text(base.get("symbol")),
        _search_text(quote.get("symbol")),
    } - {""}
    pair_liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)

    best_match: Optional[Tuple[dict, dict, float]] = None
    best_score = -1.0
    for pool in raw_pools or []:
        taxonomy = classify_defi_record(pool)
        if not taxonomy.get("supports_pool_route"):
            continue
        if _search_text(pool.get("chain")) != pair_chain:
            continue

        score = 0.0
        project = _search_text(pool.get("project"))
        if project in project_aliases:
            score += 90.0
        elif project_aliases:
            continue

        underlying_addresses = {
            _search_text(value)
            for value in (pool.get("underlying_tokens") or pool.get("underlyingTokens") or [])
            if value
        }
        if pair_addresses and underlying_addresses:
            if pair_addresses == underlying_addresses:
                score += 120.0
            elif pair_addresses.issubset(underlying_addresses):
                score += 80.0
        else:
            symbol_parts = {
                _search_text(part)
                for part in str(pool.get("symbol") or "").replace("-", "/").split("/")
                if part.strip()
            }
            if pair_symbols and pair_symbols == symbol_parts:
                score += 70.0

        pool_tvl = float(pool.get("tvl_usd") or pool.get("tvlUsd") or 0)
        if pair_liquidity > 0 and pool_tvl > 0:
            gap = abs(pool_tvl - pair_liquidity) / max(pair_liquidity, pool_tvl, 1.0)
            score += max(0.0, 35.0 - gap * 55.0)
        else:
            score += 10.0

        if score > best_score:
            best_match = (pool, taxonomy, score)
            best_score = score

    return best_match


def _pair_tvl_gap(pair: dict, pool: dict) -> float:
    pair_liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
    pool_tvl = float(pool.get("tvl_usd") or pool.get("tvlUsd") or 0)
    if pair_liquidity <= 0 or pool_tvl <= 0:
        return 1.0
    return abs(pool_tvl - pair_liquidity) / max(pair_liquidity, pool_tvl, 1.0)


def _is_trusted_pair_match(pair: dict, pool: dict, score: float) -> bool:
    pair_address = _search_text(pair.get("pairAddress"))
    pool_url = _search_text(pool.get("url"))
    if pair_address and pair_address in pool_url:
        return True

    gap = _pair_tvl_gap(pair, pool)
    if gap <= 0.35 and score >= 220:
        return True
    if gap <= 0.20:
        return True
    return False


async def analyze_token(request: web.Request) -> web.Response:
    """
    POST /api/v1/analyze

    Analyze a token with AI-powered security assessment.
    Supports all chains — auto-detected from address format.

    Request body:
        {
            "address": "token_address",
            "mode": "quick" | "standard" | "deep",
            "chain": "ethereum" | "solana" | ...  (optional)
        }
    """
    global _analyzer

    try:
        data = await request.json()

        try:
            req = AnalyzeTokenRequest(**data)
        except Exception as e:
            return web.json_response(
                ErrorResponse(
                    error="Invalid request",
                    code="INVALID_REQUEST",
                    details={"message": str(e)}
                ).model_dump(mode='json'),
                status=400
            )

        mode_map = {
            AnalysisModeType.QUICK: "quick",
            AnalysisModeType.STANDARD: "standard",
            AnalysisModeType.DEEP: "full"
        }
        mode = mode_map.get(req.mode, "standard")

        # Validate address (multi-chain aware)
        if not _analyzer or not _analyzer.is_valid_address(req.address):
            return web.json_response(
                ErrorResponse(
                    error="Invalid token address",
                    code="INVALID_ADDRESS",
                    details={"supported": "Solana base58 or EVM 0x hex address"}
                ).model_dump(mode='json'),
                status=400
            )

        logger.info(f"Web API: Analyzing {req.address[:8]}... (mode={mode}, chain={req.chain or 'auto'})")
        result = await _analyzer.analyze(req.address, mode=mode, chain=req.chain)

        if not result:
            return web.json_response(
                ErrorResponse(
                    error="Analysis failed",
                    code="ANALYSIS_FAILED",
                    details={"address": req.address}
                ).model_dump(mode='json'),
                status=500
            )

        response = convert_result_to_response(result, mode)

        # Track analysis in database
        try:
            db = await get_database()
            if db._initialized:
                await db.track_web_analysis(
                    token_address=req.address,
                    token_symbol=result.token.symbol,
                    token_name=result.token.name,
                    overall_score=result.overall_score,
                    grade=result.grade,
                    source="api"
                )
        except Exception as e:
            logger.warning(f"Failed to track analysis in DB: {e}")

        logger.info(f"Web API: Analysis complete for {result.token.symbol} - Score: {result.overall_score}")

        return web.json_response(response)

    except Exception as e:
        logger.error(f"Analysis endpoint error: {e}", exc_info=True)
        return web.json_response(
            ErrorResponse(
                error="Internal server error",
                code="INTERNAL_ERROR",
                details={"message": str(e)}
            ).model_dump(mode='json'),
            status=500
        )


async def get_token_analysis(request: web.Request) -> web.Response:
    """
    GET /api/v1/token/{address}

    Get cached analysis for a token, or return 404 if not cached.
    Optionally pass ?chain= to specify chain.
    """
    global _analyzer, _cache

    address = request.match_info.get('address')
    chain = request.query.get('chain')

    if not address:
        return web.json_response(
            ErrorResponse(error="Address required", code="MISSING_ADDRESS").model_dump(mode='json'),
            status=400
        )

    if not _analyzer or not _analyzer.is_valid_address(address):
        return web.json_response(
            ErrorResponse(error="Invalid token address", code="INVALID_ADDRESS").model_dump(mode='json'),
            status=400
        )

    # Try all modes in cache
    from src.chains.address import AddressResolver
    resolver = AddressResolver()
    chain_type = resolver.get_default_chain_for_address(address)
    chain_val = chain or (chain_type.value if chain_type else "solana")

    for mode in ["standard", "full", "quick"]:
        cache_key = f"{chain_val}:{address}:{mode}"
        if _analyzer and cache_key in _analyzer._cache:
            result = _analyzer._cache[cache_key]
            response = convert_result_to_response(result, mode, cached=True)
            return web.json_response(response)

    return web.json_response(
        ErrorResponse(
            error="Token not found in cache. Use POST /api/v1/analyze to analyze.",
            code="NOT_FOUND"
        ).model_dump(mode='json'),
        status=404
    )


async def refresh_analysis(request: web.Request) -> web.Response:
    """
    POST /api/v1/token/{address}/refresh

    Force refresh analysis for a token (clears cache).
    """
    global _analyzer

    address = request.match_info.get('address')
    mode = request.query.get('mode', 'standard')
    chain = request.query.get('chain')

    if not address:
        return web.json_response(
            ErrorResponse(error="Address required", code="MISSING_ADDRESS").model_dump(mode='json'),
            status=400
        )

    if _analyzer:
        # Clear all cache entries for this address
        for key in list(_analyzer._cache.keys()):
            if address in key:
                del _analyzer._cache[key]

    result = await _analyzer.analyze(address, mode=mode, chain=chain) if _analyzer else None

    if not result:
        return web.json_response(
            ErrorResponse(error="Analysis failed", code="ANALYSIS_FAILED").model_dump(mode='json'),
            status=500
        )

    response = convert_result_to_response(result, mode, cached=False)
    return web.json_response(response)


async def search_tokens(request: web.Request) -> web.Response:
    """
    GET /api/v1/search?query=...&chain=...

    Universal search across tokens, protocols, wallets.
    Auto-detects input type (address, ENS, search query).
    """
    from src.data.dexscreener import DexScreenerClient
    from src.data.defillama import DefiLlamaClient
    from src.chains.address import AddressResolver
    from src.api.schemas.responses import SearchResultItem

    query = request.query.get('query', '')
    chain = request.query.get('chain')
    try:
        limit = min(int(request.query.get('limit', 10)), 50)
    except (TypeError, ValueError):
        return web.json_response(
            ErrorResponse(error="Invalid limit parameter", code="INVALID_QUERY").model_dump(mode='json'),
            status=400,
        )

    if not query or len(query) < 2:
        return web.json_response(
            ErrorResponse(error="Query must be at least 2 characters", code="INVALID_QUERY").model_dump(mode='json'),
            status=400
        )

    resolver = AddressResolver()
    address_candidates = _address_candidates_from_query(query)
    resolved_query = address_candidates[0] if address_candidates else query
    input_type = resolver.detect_input_type(resolved_query)
    query_lower = resolved_query.strip().lower()

    try:
        results = []
        seen_urls = set()
        exact_pool_match_found = False

        async with DexScreenerClient() as client:
            dex_task = client.search_tokens(resolved_query, limit=limit, chain=chain)
            pair_task = client.find_pair(resolved_query, chain=chain) if (input_type in ("evm_address", "solana_address") or address_candidates) else None

            llama = request.app.get("defi_llama")
            close_llama = False
            if llama is None:
                llama = DefiLlamaClient()
                close_llama = True

            try:
                pool_task = llama.get_pools(min_tvl=0, min_apy=0)
                if pair_task:
                    dex_results, raw_pools, pair_match = await asyncio.gather(dex_task, pool_task, pair_task)
                else:
                    dex_results, raw_pools = await asyncio.gather(dex_task, pool_task)
                    pair_match = None
            finally:
                if close_llama:
                    await llama.close()

        if pair_match:
            resolved_pool = _resolve_pool_from_pair(pair_match, raw_pools or [])
            pair_address = str(pair_match.get("pairAddress") or resolved_query)
            pair_chain = str(pair_match.get("chainId") or chain or "")
            if resolved_pool and _is_trusted_pair_match(pair_match, resolved_pool[0], resolved_pool[2]):
                matched_pool, taxonomy, _ = resolved_pool
                pool_id = str(matched_pool.get("pool_id") or matched_pool.get("pool") or "")
                if pool_id:
                    url = f"/pool/{quote(pool_id, safe='')}?pair={quote(pair_address, safe='')}&chain={quote(str(pair_match.get('chainId') or ''), safe='')}"
                    tvl = float(matched_pool.get("tvl_usd") or matched_pool.get("tvlUsd") or 0)
                    apy = float(matched_pool.get("apy") or 0)
                    chain_label = str(matched_pool.get("chain") or pair_match.get("chainId") or "Unknown")
                    project = str(matched_pool.get("project") or pair_match.get("dexId") or "Unknown")
                    symbol = str(matched_pool.get("symbol") or f"{pair_match.get('baseToken', {}).get('symbol', '?')}-{pair_match.get('quoteToken', {}).get('symbol', '?')}")
                    results.append(SearchResultItem(
                        type="pool",
                        product_type=str(taxonomy.get("product_type") or ""),
                        title=f"{symbol} on {project}",
                        subtitle=f"Exact pool match · {'Farm' if taxonomy.get('is_incentivized') else 'LP Pool'} · {chain_label} · TVL ${tvl:,.0f} · APY {apy:.2f}%",
                        address=pool_id,
                        chain=str(chain_label).lower(),
                        score=260,
                        url=url,
                        logo=None,
                    ).model_dump())
                    seen_urls.add(url)
                    exact_pool_match_found = True
            else:
                base_token = pair_match.get("baseToken") or {}
                quote_token = pair_match.get("quoteToken") or {}
                stable_symbols = {"USDC", "USDT", "DAI", "FDUSD", "USDE", "BUSD", "TUSD", "FRAX", "LUSD"}
                ordered_symbols = [quote_token.get("symbol"), base_token.get("symbol")] if str(quote_token.get("symbol") or "").upper() in stable_symbols else [base_token.get("symbol"), quote_token.get("symbol")]
                symbol = "-".join(part for part in ordered_symbols if part) or f"{base_token.get('symbol', '?')}-{quote_token.get('symbol', '?')}"
                title = f"{symbol} on {pair_match.get('dexId') or 'DEX'}"
                tvl = float((pair_match.get("liquidity") or {}).get("usd") or 0)
                volume = float((pair_match.get("volume") or {}).get("h24") or 0)
                url = f"/pool/{quote(pair_address, safe='')}?pair={quote(pair_address, safe='')}&chain={quote(pair_chain, safe='')}&source=dexpair"
                results.append(SearchResultItem(
                    type="pool",
                    product_type="direct_dex_pair",
                    title=title,
                    subtitle=f"Exact DEX pair · {str(pair_chain).upper()} · TVL ${tvl:,.0f} · 24h Volume ${volume:,.0f}",
                    address=pair_address,
                    chain=str(pair_chain).lower(),
                    score=255,
                    url=url,
                    logo=None,
                ).model_dump())
                seen_urls.add(url)
                exact_pool_match_found = True

        if input_type in ("evm_address", "solana_address") and not exact_pool_match_found:
            detected_chain = resolver.get_default_chain_for_address(resolved_query)
            chain_name = chain or (detected_chain.value if detected_chain else "solana")
            direct_token = SearchResultItem(
                type="token",
                title=f"Token {resolved_query[:8]}...",
                subtitle=f"Direct address on {chain_name}",
                address=resolved_query,
                chain=chain_name,
                score=180 if pair_match else 220,
                url=f"/token/{resolved_query}?chain={chain_name}",
            ).model_dump()
            if direct_token["url"] not in seen_urls:
                results.append(direct_token)
                seen_urls.add(direct_token["url"])

        for r in ([] if exact_pool_match_found else dex_results[:limit]):
            result_chain = r.get('chain')
            url = f"/token/{r.get('address')}" + (f"?chain={result_chain}" if result_chain else "")
            if url in seen_urls:
                continue
            results.append(SearchResultItem(
                type="token",
                title=f"{r.get('name', '?')} ({r.get('symbol', '?')})",
                subtitle=f"{str(result_chain or 'unknown').upper()} · {r.get('dex', '')}",
                address=r.get('address'),
                chain=result_chain,
                score=95,
                url=url,
                logo=r.get('logo_url'),
            ).model_dump())
            seen_urls.add(url)

        matching_pools = []
        for pool in raw_pools or []:
            taxonomy = classify_defi_record(pool)
            if not taxonomy.get("supports_pool_route"):
                continue
            pool_chain = _search_text(pool.get("chain"))
            if chain and pool_chain != chain.lower():
                continue
            score = _pool_search_score(pool, query_lower)
            if score < 0:
                continue
            matching_pools.append((score, pool, taxonomy))

        matching_pools.sort(key=lambda item: item[0], reverse=True)
        for score, pool, taxonomy in matching_pools[:limit]:
            pool_id = str(pool.get("pool_id") or pool.get("pool") or "")
            if not pool_id:
                continue
            url = f"/pool/{quote(pool_id, safe='')}"
            if url in seen_urls:
                continue
            chain_label = str(pool.get("chain") or "Unknown")
            project = str(pool.get("project") or "Unknown")
            symbol = str(pool.get("symbol") or "Unknown")
            tvl = float(pool.get("tvl_usd") or pool.get("tvlUsd") or 0)
            apy = float(pool.get("apy") or 0)
            title = f"{symbol} on {project}"
            subtitle = f"{'Farm' if taxonomy.get('is_incentivized') else 'LP Pool'} · {chain_label} · TVL ${tvl:,.0f} · APY {apy:.2f}%"
            results.append(SearchResultItem(
                type="pool",
                product_type=str(taxonomy.get("product_type") or ""),
                title=title,
                subtitle=subtitle,
                address=pool_id,
                chain=chain_label.lower(),
                score=round(score, 2),
                url=url,
                logo=None,
            ).model_dump())
            seen_urls.add(url)

        results.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        results = results[:limit]

        return web.json_response({
            "query": query,
            "input_type": input_type,
            "results": results,
            "count": len(results),
            "total": len(results),
        })

    except Exception as e:
        logger.error(f"Search error: {e}")
        return web.json_response(
            ErrorResponse(error="Search failed", code="SEARCH_FAILED").model_dump(mode='json'),
            status=500
        )


def setup_analysis_routes(app: web.Application):
    """Setup analysis API routes"""
    app.router.add_post('/api/v1/analyze', analyze_token)
    app.router.add_get('/api/v1/token/{address}', get_token_analysis)
    app.router.add_post('/api/v1/token/{address}/refresh', refresh_analysis)
    app.router.add_get('/api/v1/search', search_tokens)

    app.on_startup.append(init_analyzer)
    app.on_cleanup.append(cleanup_analyzer)

    logger.info("Analysis routes registered (multi-chain)")
