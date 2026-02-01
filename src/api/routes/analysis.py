"""
Token analysis API routes.

Provides endpoints for token analysis, including quick and deep analysis modes.
"""

import logging
from aiohttp import web
from datetime import datetime
from typing import Optional

from src.core.analyzer import TokenAnalyzer
from src.core.models import AnalysisResult, TokenInfo
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


async def init_analyzer(app: web.Application):
    """Initialize analyzer on app startup"""
    global _analyzer, _cache
    _analyzer = TokenAnalyzer()
    _cache = CacheLayer()
    app['analyzer'] = _analyzer
    app['cache'] = _cache
    logger.info("TokenAnalyzer initialized for web API")


async def cleanup_analyzer(app: web.Application):
    """Cleanup analyzer on app shutdown"""
    global _analyzer
    if _analyzer:
        await _analyzer.close()
        logger.info("TokenAnalyzer closed")


def convert_result_to_response(result: AnalysisResult, mode: str, cached: bool = False) -> dict:
    """Convert AnalysisResult to API response dict"""
    token = result.token

    return AnalysisResponse(
        token=TokenBasicInfo(
            address=token.address,
            name=token.name,
            symbol=token.symbol,
            decimals=token.decimals,
            logo_url=token.logo_url
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
            honeypot_status=token.honeypot_status,
            honeypot_is_honeypot=token.honeypot_is_honeypot,
            honeypot_sell_tax_percent=token.honeypot_sell_tax_percent,
            honeypot_explanation=token.honeypot_explanation,
            honeypot_warnings=token.honeypot_warnings
        ),
        holders=HolderAnalysisResponse(
            top_holder_pct=token.top_holder_pct,
            holder_concentration=token.holder_concentration,
            suspicious_wallets=token.suspicious_wallets,
            dev_wallet_risk=token.dev_wallet_risk,
            holder_flags=token.holder_flags,
            top_holders=token.top_holders[:10]  # Top 10 only
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

    Analyze a Solana token with AI-powered security assessment.

    Request body:
        {
            "address": "token_address",
            "mode": "quick" | "standard" | "deep"
        }

    Returns:
        Full analysis response or error
    """
    global _analyzer

    try:
        data = await request.json()

        # Validate request
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

        # Map mode
        mode_map = {
            AnalysisModeType.QUICK: "quick",
            AnalysisModeType.STANDARD: "standard",
            AnalysisModeType.DEEP: "full"
        }
        mode = mode_map.get(req.mode, "standard")

        # Validate address format
        if not _analyzer.is_valid_address(req.address):
            return web.json_response(
                ErrorResponse(
                    error="Invalid Solana address",
                    code="INVALID_ADDRESS"
                ).model_dump(mode='json'),
                status=400
            )

        # Run analysis
        logger.info(f"Web API: Analyzing {req.address[:8]}... (mode={mode})")
        result = await _analyzer.analyze(req.address, mode=mode)

        if not result:
            return web.json_response(
                ErrorResponse(
                    error="Analysis failed",
                    code="ANALYSIS_FAILED",
                    details={"address": req.address}
                ).model_dump(mode='json'),
                status=500
            )

        # Convert to response
        response = convert_result_to_response(result, mode)

        # Track analysis in database for accurate stats
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
    """
    global _analyzer, _cache

    address = request.match_info.get('address')

    if not address:
        return web.json_response(
            ErrorResponse(error="Address required", code="MISSING_ADDRESS").model_dump(mode='json'),
            status=400
        )

    # Check if valid address
    if not _analyzer.is_valid_address(address):
        return web.json_response(
            ErrorResponse(error="Invalid Solana address", code="INVALID_ADDRESS").model_dump(mode='json'),
            status=400
        )

    # Check cache
    cache_key = f"{address}:standard"
    if cache_key in _analyzer._cache:
        result = _analyzer._cache[cache_key]
        response = convert_result_to_response(result, "standard", cached=True)
        return web.json_response(response)

    # Not in cache
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

    if not address:
        return web.json_response(
            ErrorResponse(error="Address required", code="MISSING_ADDRESS").model_dump(mode='json'),
            status=400
        )

    # Clear cache
    for key in list(_analyzer._cache.keys()):
        if key.startswith(address):
            del _analyzer._cache[key]

    # Run fresh analysis
    result = await _analyzer.analyze(address, mode=mode)

    if not result:
        return web.json_response(
            ErrorResponse(error="Analysis failed", code="ANALYSIS_FAILED").model_dump(mode='json'),
            status=500
        )

    response = convert_result_to_response(result, mode, cached=False)
    return web.json_response(response)


async def search_tokens(request: web.Request) -> web.Response:
    """
    GET /api/v1/search?query=...

    Search for tokens by name or address.
    Uses DexScreener search API.
    """
    from src.data.dexscreener import DexScreenerClient

    query = request.query.get('query', '')
    limit = min(int(request.query.get('limit', 10)), 50)

    if not query or len(query) < 2:
        return web.json_response(
            ErrorResponse(error="Query must be at least 2 characters", code="INVALID_QUERY").model_dump(mode='json'),
            status=400
        )

    try:
        async with DexScreenerClient() as client:
            results = await client.search_tokens(query, limit=limit)

        return web.json_response({
            "results": results,
            "query": query,
            "count": len(results)
        })

    except Exception as e:
        logger.error(f"Search error: {e}")
        return web.json_response(
            ErrorResponse(error="Search failed", code="SEARCH_FAILED").model_dump(mode='json'),
            status=500
        )


def setup_analysis_routes(app: web.Application):
    """Setup analysis API routes"""
    # Analysis endpoints
    app.router.add_post('/api/v1/analyze', analyze_token)
    app.router.add_get('/api/v1/token/{address}', get_token_analysis)
    app.router.add_post('/api/v1/token/{address}/refresh', refresh_analysis)
    app.router.add_get('/api/v1/search', search_tokens)

    # Lifecycle hooks
    app.on_startup.append(init_analyzer)
    app.on_cleanup.append(cleanup_analyzer)

    logger.info("Analysis routes registered")
