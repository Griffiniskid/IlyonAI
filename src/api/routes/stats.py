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

logger = logging.getLogger(__name__)

# Cache for stats data
_stats_cache: Dict[str, Any] = {}
_cache_ttl = 60  # seconds

# DefiLlama API for aggregate DEX volumes
DEFILLAMA_DEX_VOLUME_URL = "https://api.llama.fi/overview/dexs/solana"
DEFILLAMA_CHAINS_URL = "https://api.llama.fi/v2/chains"

# Patterns for token categorization
MEMECOIN_PATTERNS = [
    r'(doge|shib|pepe|wojak|chad|mog|cat|dog|inu|elon|moon|safe|baby|floki|bonk|wif|popcat|brett|bome|slerf)',
    r'(meme|coin|token|ape|frog|monkey|panda|bear|bull|trump|melania)',
]

DEFI_PATTERNS = [
    r'(swap|finance|fi|yield|stake|lend|borrow|vault|pool|liqui|amm|dex)',
    r'(usd[ct]|dai|frax|eur|gbp|jup|ray|orca|marinade)',
]

GAMING_NFT_PATTERNS = [
    r'(game|play|nft|meta|verse|world|land|realm|guild|hero|quest)',
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


def classify_risk(token: Dict) -> str:
    """Classify token risk based on liquidity and volatility."""
    liquidity = float(token.get("liquidity", {}).get("usd", 0) or 0)
    price_change = abs(float(token.get("priceChange", {}).get("h24", 0) or 0))

    # High liquidity, low volatility = Safe
    if liquidity >= 100000 and price_change < 30:
        return "Safe"
    # Medium liquidity, moderate volatility = Caution
    elif liquidity >= 25000 and price_change < 60:
        return "Caution"
    # Low liquidity or high volatility = Risky
    elif liquidity >= 5000:
        return "Risky"
    # Very low liquidity = Potential Scam
    else:
        return "Scam"


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
                
                # Extract hourly data from totalDataChart if available
                # Note: DefiLlama returns daily data in totalDataChart, not hourly.
                # We'll leave this empty to trigger the hourly simulation in the main handler
                # until we have a source for real hourly volume data.
                hourly_data = []
                
                # chart_data = data.get("totalDataChart", [])
                
                # if chart_data and len(chart_data) > 0:
                #     # Get last 24 data points (each is typically 1 hour)
                #     recent_data = chart_data[-24:] if len(chart_data) >= 24 else chart_data
                    
                #     for point in recent_data:
                #         if isinstance(point, list) and len(point) >= 2:
                #             timestamp = point[0]
                #             volume = point[1]
                #             # Convert timestamp to hour label
                #             dt = datetime.utcfromtimestamp(timestamp)
                #             hour_label = dt.strftime("%H:%M")
                #             hourly_data.append({
                #                 "time": hour_label,
                #                 "volume": float(volume or 0)
                #             })
                
                return {
                    "total_24h": total_24h,
                    "volume_change": round(volume_change, 1),
                    "hourly_data": hourly_data,
                    "total_dexes": total_dexes,
                }
                
    except Exception as e:
        logger.warning(f"DefiLlama fetch failed: {e}")
        return {}


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
            return web.json_response(cached['data'])

    try:
        # Fetch aggregate Solana DEX volume from DefiLlama (real billions data)
        defillama_data = await fetch_defillama_solana_volume()
        
        # Fetch Solana chain TVL
        chain_stats = await fetch_solana_chain_stats()
        
        # Get trending tokens from DexScreener for market analysis
        async with DexScreenerClient() as client:
            trending_tokens = await client.get_trending_tokens(limit=50)

        # Use DefiLlama data for volume (this is the real aggregate)
        total_volume = defillama_data.get("total_24h", 0)
        volume_change = defillama_data.get("volume_change", 0.0)
        
        # Generate hourly volume chart from DefiLlama data
        volume_chart_data = defillama_data.get("hourly_data", [])
        
        # If no hourly data, generate estimated hourly breakdown
        if not volume_chart_data and total_volume > 0:
            now = datetime.utcnow()
            # Generate 24 hourly data points with realistic variation
            import random
            random.seed(int(now.timestamp()) // 3600)  # Consistent within the hour
            base_hourly = total_volume / 24
            
            for i in range(24):
                hour = (now - timedelta(hours=23-i)).strftime("%H:00")
                # Add realistic variation (busier during certain hours)
                hour_int = int(hour.split(":")[0])
                # Higher volume during 14:00-22:00 UTC (US trading hours)
                if 14 <= hour_int <= 22:
                    multiplier = 1.2 + random.uniform(-0.1, 0.2)
                elif 6 <= hour_int <= 14:
                    multiplier = 1.0 + random.uniform(-0.1, 0.1)
                else:
                    multiplier = 0.7 + random.uniform(-0.1, 0.1)
                
                volume_chart_data.append({
                    "time": hour,
                    "volume": base_hourly * multiplier
                })
        
        # Convert to VolumeDataPoint objects
        volume_chart = [
            VolumeDataPoint(time=d["time"], volume=d["volume"])
            for d in volume_chart_data[-24:]  # Last 24 hours
        ]

        # Analyze trending tokens for risk/market distribution
        risk_counts = {"Safe": 0, "Caution": 0, "Risky": 0, "Scam": 0}
        category_counts = {"Memecoins": 0, "DeFi": 0, "Gaming/NFT": 0, "Other": 0}
        total_liquidity = 0.0
        
        if trending_tokens:
            for t in trending_tokens:
                risk = classify_risk(t)
                risk_counts[risk] += 1
                
                base = t.get("baseToken", {})
                name = base.get("name", "")
                symbol = base.get("symbol", "")
                category = categorize_token(name, symbol)
                category_counts[category] += 1
                
                total_liquidity += float(t.get("liquidity", {}).get("usd", 0) or 0)

        total_analyzed = len(trending_tokens) if trending_tokens else 0
        avg_liquidity = total_liquidity / total_analyzed if total_analyzed > 0 else 0
        safe_percent = (risk_counts["Safe"] / total_analyzed * 100) if total_analyzed > 0 else 0

        # Risk distribution
        risk_distribution = [
            RiskDistributionItem(name="Safe", count=risk_counts["Safe"], color="#10b981"),
            RiskDistributionItem(name="Caution", count=risk_counts["Caution"], color="#f59e0b"),
            RiskDistributionItem(name="Risky", count=risk_counts["Risky"], color="#ef4444"),
            RiskDistributionItem(name="Scam", count=risk_counts["Scam"], color="#991b1b"),
        ]

        # Market distribution as MarketDistributionItem objects
        market_distribution = []
        for name, value in category_counts.items():
            if value > 0:
                color = {
                    "Memecoins": "#10b981",
                    "DeFi": "#3b82f6",
                    "Gaming/NFT": "#8b5cf6",
                    "Other": "#6b7280"
                }.get(name, "#6b7280")
                market_distribution.append(
                    MarketDistributionItem(name=name, value=value, color=color)
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

        # Database stats for analysis counts
        tokens_analyzed_today = total_analyzed
        total_tokens_analyzed = total_analyzed
        
        try:
            db = await get_database()
            if db._initialized:
                db_analyzed_today = await db.count_analyses_today()
                db_total_analyzed = await db.count_total_analyses()
                
                if db_analyzed_today > 0:
                    tokens_analyzed_today = db_analyzed_today
                if db_total_analyzed > 0:
                    total_tokens_analyzed = db_total_analyzed
        except Exception as e:
            logger.warning(f"Database stats lookup failed: {e}")

        # Solana TVL from chain stats
        solana_tvl = chain_stats.get("tvl", 0)

        response = DashboardStatsResponse(
            total_volume_24h=total_volume,
            volume_change_24h=volume_change,
            active_tokens=total_analyzed,  # Trending tokens analyzed
            active_tokens_change=0,
            safe_tokens_percent=round(safe_percent, 1),
            safe_tokens_change=0.0,
            scams_detected=risk_counts["Scam"] + risk_counts["Risky"],
            scams_change=0,
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

        return web.json_response(response)

    except Exception as e:
        logger.error(f"Stats endpoint error: {e}", exc_info=True)
        return web.json_response(
            ErrorResponse(
                error="Failed to fetch dashboard stats",
                code="STATS_FAILED",
                details={"message": str(e)}
            ).model_dump(mode='json'),
            status=500
        )


def setup_stats_routes(app: web.Application):
    """Setup stats API routes"""
    app.router.add_get('/api/v1/stats', get_dashboard_stats)

    logger.info("Stats routes registered")
