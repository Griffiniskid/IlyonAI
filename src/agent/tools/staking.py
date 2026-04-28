from src.agent.tools._base import ok_envelope, err_envelope


async def get_staking_options(ctx, *, chain=None, asset=None, limit=10,
                              min_tvl: float = 50_000_000.0,
                              min_apy: float = 0.5,
                              max_apy: float = 500.0):
    """Get real staking and yield opportunities from DefiLlama."""
    pools = []
    
    if hasattr(ctx.services, "defillama") and ctx.services.defillama:
        try:
            # Map chain string to ChainType if needed
            chain_type = None
            if chain:
                from src.chains.base import ChainType
                chain_map = {
                    "ethereum": ChainType.ETHEREUM,
                    "eth": ChainType.ETHEREUM,
                    "solana": ChainType.SOLANA,
                    "sol": ChainType.SOLANA,
                    "bsc": ChainType.BSC,
                    "polygon": ChainType.POLYGON,
                    "arbitrum": ChainType.ARBITRUM,
                    "optimism": ChainType.OPTIMISM,
                    "avalanche": ChainType.AVALANCHE,
                    "base": ChainType.BASE,
                }
                chain_type = chain_map.get(chain.lower())
            
            # Get pools from DefiLlama with a strong TVL floor.
            all_pools = await ctx.services.defillama.get_pools(
                chain=chain_type,
                min_tvl=max(min_tvl, 1_000_000),
                min_apy=min_apy,
            )

            # Filter for staking/liquid staking if asset specified
            if asset:
                asset_lower = asset.lower()
                all_pools = [p for p in all_pools if asset_lower in p.get("symbol", "").lower()]

            # Drop pools with absurd APY (often stale / manipulated / broken math).
            all_pools = [p for p in all_pools if (p.get("apy") or 0) <= max_apy]

            # Rank: prefer high TVL × sane APY. Avoids selecting 800,000% APY pools
            # on a $600k TVL rug.
            def _score(p):
                apy = float(p.get("apy") or 0)
                tvl = float(p.get("tvlUsd") or 0)
                # Log-TVL × APY blend, with an APY ceiling so outliers don't dominate.
                import math
                if tvl <= 0:
                    return 0.0
                return math.log10(tvl) * min(apy, 40.0)

            all_pools.sort(key=_score, reverse=True)
            pools = all_pools[:limit]
            
        except Exception as e:
            print(f"DefiLlama staking error: {e}")
    
    if pools:
        # Format pools for display
        formatted_pools = []
        for pool in pools:
            formatted_pools.append({
                "protocol": pool.get("project", "Unknown"),
                "pool": pool.get("pool", ""),
                "chain": pool.get("chain", "Unknown"),
                "symbol": pool.get("symbol", ""),
                "apy": pool.get("apy", 0),
                "apy_base": pool.get("apyBase", 0),
                "apy_reward": pool.get("apyReward", 0),
                "tvl_usd": pool.get("tvlUsd", 0),
                "risk_level": _calculate_risk(pool),
            })
        
        data = {
            "staking_options": formatted_pools,
            "count": len(formatted_pools),
            "source": "DefiLlama",
        }
        return ok_envelope(data=data, card_type="stake", card_payload=data)
    
    return err_envelope(
        "no_staking_data",
        "No staking pools found matching your criteria. Try a different chain or asset.",
        card_type="stake"
    )


def _calculate_risk(pool: dict) -> str:
    """Calculate risk level based on TVL and protocol maturity."""
    tvl = pool.get("tvlUsd", 0) or 0
    if tvl > 100_000_000:  # $100M+
        return "LOW"
    elif tvl > 10_000_000:  # $10M+
        return "MEDIUM"
    else:
        return "HIGH"
