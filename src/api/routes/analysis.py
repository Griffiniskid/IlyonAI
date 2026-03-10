"""
Token analysis API routes — multi-chain.

Provides endpoints for token analysis across all supported chains.
"""

import logging
from aiohttp import web
from datetime import datetime
from typing import Optional

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
    from src.chains.address import AddressResolver
    from src.api.schemas.responses import SearchResultItem, UniversalSearchResponse

    query = request.query.get('query', '')
    chain = request.query.get('chain')
    limit = min(int(request.query.get('limit', 10)), 50)

    if not query or len(query) < 2:
        return web.json_response(
            ErrorResponse(error="Query must be at least 2 characters", code="INVALID_QUERY").model_dump(mode='json'),
            status=400
        )

    resolver = AddressResolver()
    input_type = resolver.detect_input_type(query)

    try:
        results = []

        if input_type in ("evm_address", "solana_address"):
            # Direct address lookup — return as single token result
            detected_chain = resolver.get_default_chain_for_address(query)
            chain_name = chain or (detected_chain.value if detected_chain else "solana")
            results.append(SearchResultItem(
                type="token",
                title=f"Token {query[:8]}...",
                subtitle=f"Direct address on {chain_name}",
                address=query,
                chain=chain_name,
                url=f"/token/{query}?chain={chain_name}",
            ).model_dump())
        else:
            # Name/symbol search via DexScreener
            async with DexScreenerClient() as client:
                dex_results = await client.search_tokens(query, limit=limit, chain=chain)

            for r in dex_results:
                result_chain = r.get('chain')
                results.append(SearchResultItem(
                    type="token",
                    title=f"{r.get('name', '?')} ({r.get('symbol', '?')})",
                    subtitle=f"{str(result_chain or 'unknown').upper()} · {r.get('dex', '')}",
                    address=r.get('address'),
                    chain=result_chain,
                    url=f"/token/{r.get('address')}" + (f"?chain={result_chain}" if result_chain else ""),
                    logo=r.get('logo_url'),
                ).model_dump())

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
