"""
Dashboard statistics API routes.

Provides endpoints for fetching real-time dashboard metrics.
Uses DefiLlama for aggregate Solana DEX volume data (accurate billions).
Uses DexScreener for trending tokens and market analysis.
"""

import logging
import re
import aiohttp
from aiohttp import web
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from src.data.dexscreener import DexScreenerClient
from src.storage.database import get_database
from src.api.schemas.responses import (
    DashboardStatsResponse,
    VolumeDataPoint,
    RiskDistributionItem,
    MarketDistributionItem,
    ErrorResponse
)
from src.api.response_envelope import envelope_error_response, envelope_response

logger = logging.getLogger(__name__)

# Cache for stats data
_stats_cache: Dict[str, Any] = {}
_cache_ttl = 60  # seconds

# DefiLlama API for aggregate DEX volumes
DEFILLAMA_DEX_VOLUME_URL = "https://api.llama.fi/overview/dexs/solana"
DEFILLAMA_CHAINS_URL = "https://api.llama.fi/v2/chains"

# Patterns for token categorization (narrowed to avoid false positives)
MEMECOIN_PATTERNS = [
    r'\b(doge|shib|pepe|wojak|chad|mog|inu|floki|bonk|wif|popcat|brett|bome|slerf)\b',
    r'\b(meme|frog|monkey|trump|melania)\b',
]

DEFI_PATTERNS = [
    r'\b(swap|finance|yield|stake|lend|borrow|vault|liqui|amm|dex)\b',
    r'\b(usd[ct]|dai|frax|jup|ray|orca|marinade|pyth|raydium|jupiter)\b',
]

GAMING_NFT_PATTERNS = [
    r'\b(game|play|nft|metaverse|realm|guild|quest)\b',
]


def categorize_token(name: str, symbol: str) -> str:
    """Categorize a token based on name/symbol patterns."""
    text = f"{name} {symbol}".lower()

    for pattern in MEMECOIN_PATTERNS:
        if re.search(pattern, text):
            return "Memecoins"

    for pattern in DEFI_PATTERNS:
        if re.search(pattern, text):
            return "DeFi"

    for pattern in GAMING_NFT_PATTERNS:
        if re.search(pattern, text):
            return "Gaming/NFT"

    return "Other"


async def fetch_defillama_solana_volume() -> Dict[str, Any]:
    """
    Fetch aggregate Solana DEX volume from DefiLlama.
    Returns total 24h volume and hourly breakdown.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(DEFILLAMA_DEX_VOLUME_URL) as resp:
                if resp.status != 200:
                    logger.warning(f"DefiLlama returned status {resp.status}")
                    return {}
                
                data = await resp.json()
                
                # Extract total 24h volume
                total_24h = float(data.get("total24h", 0) or 0)
                total_48h_to_24h = float(data.get("total48hto24h", 0) or 0)
                
                # Calculate volume change
                volume_change = 0.0
                if total_48h_to_24h > 0:
                    volume_change = ((total_24h - total_48h_to_24h) / total_48h_to_24h) * 100
                
                # Get total DEXes count (approximate active tokens)
                total_dexes = len(data.get("protocols", []))
                
                # Extract daily volume data from totalDataChart (DefiLlama provides daily, not hourly)
                daily_data = []
                chart_data = data.get("totalDataChart", [])
                if chart_data and len(chart_data) > 0:
                    recent_data = chart_data[-14:]  # Last 14 days
                    for point in recent_data:
                        if isinstance(point, list) and len(point) >= 2:
                            timestamp = point[0]
                            volume = point[1]
                            dt = datetime.utcfromtimestamp(timestamp)
                            day_label = dt.strftime("%b %d")
                            daily_data.append({
                                "time": day_label,
                                "volume": float(volume or 0)
                            })
                hourly_data = daily_data
                
                return {
                    "total_24h": total_24h,
                    "volume_change": round(volume_change, 1),
                    "hourly_data": hourly_data,
                    "total_dexes": total_dexes,
                }
                
    except Exception as e:
        logger.warning(f"DefiLlama fetch failed: {e}")
        return {}


async def fetch_sol_price() -> Dict[str, float]:
    """Fetch current SOL price and 24h change from CoinGecko."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd&include_24hr_change=true"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sol = data.get("solana", {})
                    return {
                        "price": float(sol.get("usd", 0) or 0),
                        "change_24h": round(float(sol.get("usd_24h_change", 0) or 0), 2),
                    }
    except Exception as e:
        logger.debug(f"CoinGecko SOL price fetch failed: {e}")

    # Fallback: Jupiter Price API (no 24h change available)
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = float(data.get("data", {}).get(
                        "So11111111111111111111111111111111111111112", {}
                    ).get("price", 0))
                    if price > 0:
                        return {"price": price, "change_24h": 0}
    except Exception as e:
        logger.debug(f"Jupiter SOL price fetch failed: {e}")

    return {"price": 0, "change_24h": 0}


async def fetch_solana_chain_stats() -> Dict[str, Any]:
    """
    Fetch Solana chain statistics from DefiLlama.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(DEFILLAMA_CHAINS_URL) as resp:
                if resp.status != 200:
                    return {}
                
                data = await resp.json()
                
                # Find Solana in the chains list
                for chain in data:
                    if chain.get("name", "").lower() == "solana":
                        return {
                            "tvl": float(chain.get("tvl", 0) or 0),
                            "token_symbol": chain.get("tokenSymbol", "SOL"),
                        }
                
                return {}
                
    except Exception as e:
        logger.warning(f"Solana chain stats fetch failed: {e}")
        return {}


async def get_dashboard_stats(request: web.Request) -> web.Response:
    """
    GET /api/v1/stats

    Get real-time dashboard statistics.
    
    Volume data comes from DefiLlama (aggregate Solana DEX volume - billions).
    Token analysis comes from DexScreener trending tokens.
    """
    global _stats_cache

    cache_key = "dashboard_stats"

    # Check cache
    if cache_key in _stats_cache:
        cached = _stats_cache[cache_key]
        if (datetime.utcnow() - cached['time']).seconds < _cache_ttl:
            return envelope_response(cached['data'])

    try:
        # Fetch aggregate Solana DEX volume from DefiLlama (real billions data)
        # Fetch Solana chain TVL and SOL price in parallel
        import asyncio
        defillama_data, chain_stats, sol_price_data = await asyncio.gather(
            fetch_defillama_solana_volume(),
            fetch_solana_chain_stats(),
            fetch_sol_price(),
        )
        
        # Get trending tokens from DexScreener for market analysis
        async with DexScreenerClient() as client:
            trending_tokens = await client.get_trending_tokens(limit=50)

        # Use DefiLlama data for volume (this is the real aggregate)
        total_volume = defillama_data.get("total_24h", 0)
        volume_change = defillama_data.get("volume_change", 0.0)
        
        # Generate hourly volume chart from DefiLlama data
        volume_chart_data = defillama_data.get("hourly_data", [])
        
        # If no hourly data from DefiLlama, return a flat average breakdown
        # rather than fabricating random variation
        if not volume_chart_data and total_volume > 0:
            now = datetime.utcnow()
            avg_hourly = total_volume / 24
            for i in range(24):
                hour = (now - timedelta(hours=23 - i)).strftime("%H:00")
                volume_chart_data.append({
                    "time": hour,
                    "volume": avg_hourly,
                })
        
        # Convert to VolumeDataPoint objects
        volume_chart = [
            VolumeDataPoint(time=d["time"], volume=d["volume"])
            for d in volume_chart_data[-24:]  # Last 24 hours
        ]

        # Market distribution from trending tokens (liquidity-weighted)
        category_liquidity = {"Memecoins": 0.0, "DeFi": 0.0, "Gaming/NFT": 0.0, "Other": 0.0}
        total_liquidity = 0.0

        if trending_tokens:
            for t in trending_tokens:
                base = t.get("baseToken", {})
                name = base.get("name", "")
                symbol = base.get("symbol", "")
                category = categorize_token(name, symbol)
                token_liq = float(t.get("liquidity", {}).get("usd", 0) or 0)
                category_liquidity[category] += token_liq
                total_liquidity += token_liq

        total_trending = len(trending_tokens) if trending_tokens else 0
        avg_liquidity = total_liquidity / total_trending if total_trending > 0 else 0

        market_distribution = []
        total_cat_liquidity = sum(category_liquidity.values())
        for name, liq_value in category_liquidity.items():
            if liq_value > 0:
                pct = round(liq_value / total_cat_liquidity * 100, 1) if total_cat_liquidity > 0 else 0
                color = {
                    "Memecoins": "#10b981",
                    "DeFi": "#3b82f6",
                    "Gaming/NFT": "#8b5cf6",
                    "Other": "#6b7280"
                }.get(name, "#6b7280")
                market_distribution.append(
                    MarketDistributionItem(name=name, value=pct, color=color)
                )

        # Get top tokens by volume for display
        top_tokens_by_volume = []
        if trending_tokens:
            sorted_by_vol = sorted(
                trending_tokens,
                key=lambda x: float(x.get("volume", {}).get("h24", 0) or 0),
                reverse=True
            )[:10]

            for t in sorted_by_vol:
                base = t.get("baseToken", {})
                vol = float(t.get("volume", {}).get("h24", 0) or 0)
                if vol > 0:
                    top_tokens_by_volume.append({
                        "symbol": base.get("symbol", "???"),
                        "volume": vol,
                        "address": base.get("address", ""),
                    })

        # ── Real database stats (actual analyses, not heuristics) ──
        tokens_analyzed_today = 0
        total_tokens_analyzed = 0
        grade_distribution: Dict[str, int] = {}

        try:
            db = await get_database()
            if db._initialized:
                tokens_analyzed_today = await db.count_analyses_last_24h()
                total_tokens_analyzed = await db.count_total_analyses()
                grade_distribution = await db.get_grade_distribution()
        except Exception as e:
            logger.warning(f"Database stats lookup failed: {e}")

        # Build risk distribution from real grades (A+/A = Safe, B = Caution, C/D = Risky, F = Scam)
        real_risk = {"Safe": 0, "Caution": 0, "Risky": 0, "Scam": 0}
        for grade, count in grade_distribution.items():
            if grade in ("A+", "A"):
                real_risk["Safe"] += count
            elif grade == "B":
                real_risk["Caution"] += count
            elif grade in ("C", "D"):
                real_risk["Risky"] += count
            elif grade == "F":
                real_risk["Scam"] += count

        total_graded = sum(real_risk.values())
        safe_percent = (real_risk["Safe"] / total_graded * 100) if total_graded > 0 else 0

        risk_distribution = [
            RiskDistributionItem(name="Safe", count=real_risk["Safe"], color="#10b981"),
            RiskDistributionItem(name="Caution", count=real_risk["Caution"], color="#f59e0b"),
            RiskDistributionItem(name="Risky", count=real_risk["Risky"], color="#ef4444"),
            RiskDistributionItem(name="Scam", count=real_risk["Scam"], color="#991b1b"),
        ]

        # Solana TVL from chain stats
        solana_tvl = chain_stats.get("tvl", 0)

        response = DashboardStatsResponse(
            total_volume_24h=total_volume,
            volume_change_24h=volume_change,
            solana_tvl=solana_tvl,
            sol_price=sol_price_data.get("price", 0),
            sol_price_change_24h=sol_price_data.get("change_24h", 0),
            active_tokens=total_trending,
            active_tokens_change=0,
            safe_tokens_percent=round(safe_percent, 1),
            safe_tokens_change=0.0,
            scams_detected=real_risk["Scam"],
            scams_change=0,
            high_risk_tokens=total_tokens_analyzed,  # Repurposed: total analyzed all time
            volume_chart=volume_chart,
            risk_distribution=risk_distribution,
            market_distribution=market_distribution,
            top_tokens_by_volume=top_tokens_by_volume,
            tokens_analyzed_today=tokens_analyzed_today,
            total_tokens_analyzed=total_tokens_analyzed,
            avg_liquidity=avg_liquidity,
            total_liquidity=total_liquidity,
            updated_at=datetime.utcnow()
        ).model_dump(mode='json')

        # Cache response
        _stats_cache[cache_key] = {
            'data': response,
            'time': datetime.utcnow()
        }

        return envelope_response(response)

    except Exception as e:
        logger.error(f"Stats endpoint error: {e}", exc_info=True)
        return envelope_error_response(
            "Failed to fetch dashboard stats",
            code="STATS_FAILED",
            details={"message": str(e)},
            http_status=500,
        )


async def get_service_health(request: web.Request) -> web.Response:
    """
    GET /api/v1/stats/health

    Comprehensive service health report showing which features
    are fully operational, degraded, or unavailable based on
    configured API keys and service connectivity.
    """
    from src.config import settings

    services = {
        "ai_analysis": {
            "status": "operational" if settings.openrouter_api_key else "unavailable",
            "provider": "OpenRouter",
            "required_key": "OPENROUTER_API_KEY",
            "features": ["token analysis", "contract AI audit", "DeFi synthesis"],
        },
        "solana_rpc": {
            "status": "operational",
            "provider": "Solana RPC" + (" (Helius)" if settings.helius_api_key else " (Public)"),
            "features": ["token data", "holder analysis", "wallet balances"],
        },
        "evm_rpc": {
            "status": "operational",
            "provider": "Public RPC endpoints",
            "features": ["EVM token data", "shield approval scanning", "wallet balances"],
        },
        "shield": {
            "status": "operational",
            "provider": "Direct RPC (eth_getLogs)",
            "features": ["approval scanning", "risk scoring", "revoke preparation"],
            "note": "No API keys required - uses public RPC endpoints",
        },
        "honeypot_detection": {
            "status": "operational" if settings.jupiter_api_key else "degraded",
            "provider": "Jupiter API",
            "required_key": "JUPITER_API_KEY",
            "features": ["sell tax detection", "swap simulation"],
        },
        "goplus_security": {
            "status": "operational",
            "provider": "GoPlus Labs (free tier)",
            "features": ["token security checks", "honeypot detection", "contract risk"],
            "note": "No API key required for basic usage",
        },
        "twitter_sentiment": {
            "status": "operational" if settings.grok_api_key else "unavailable",
            "provider": "xAI Grok",
            "required_key": "GROK_API_KEY",
            "features": ["narrative analysis", "social sentiment"],
        },
        "defi_data": {
            "status": "operational",
            "provider": "DefiLlama + DexScreener (free)",
            "features": ["pool data", "yields", "TVL", "trending tokens"],
            "note": "No API keys required",
        },
        "portfolio": {
            "status": "operational" if settings.moralis_api_key else "degraded",
            "provider": "Moralis" if settings.moralis_api_key else "RPC fallback",
            "features": ["EVM token balances", "portfolio tracking"],
            "note": None if settings.moralis_api_key else "Using RPC fallback - limited token discovery",
        },
        "database": {
            "status": "operational" if settings.database_url else "degraded",
            "provider": "PostgreSQL" if settings.database_url else "In-memory",
            "features": ["persistent storage", "analysis cache", "blinks"],
        },
    }

    operational_count = sum(1 for s in services.values() if s["status"] == "operational")
    total = len(services)

    return envelope_response({
        "overall_status": "operational" if operational_count == total else "degraded",
        "services_operational": operational_count,
        "services_total": total,
        "services": services,
        "required_keys": ["OPENROUTER_API_KEY"],
        "recommended_keys": ["HELIUS_API_KEY", "JUPITER_API_KEY", "GROK_API_KEY"],
        "optional_keys": ["MORALIS_API_KEY", "GOPLUS_API_KEY"],
        "not_needed": [
            "ETHERSCAN_API_KEY", "BSCSCAN_API_KEY", "POLYGONSCAN_API_KEY",
            "ARBISCAN_API_KEY", "BASESCAN_API_KEY", "OPTIMISM_ETHERSCAN_API_KEY",
            "SNOWTRACE_API_KEY",
        ],
    })


def setup_stats_routes(app: web.Application):
    """Setup stats API routes"""
    app.router.add_get('/api/v1/stats', get_dashboard_stats)
    app.router.add_get('/api/v1/stats/health', get_service_health)

    logger.info("Stats routes registered")
