from src.agent.tools._base import ok_envelope, err_envelope


async def get_staking_options(ctx, *, chain=None, asset=None, limit=10):
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
            
            # Get pools from DefiLlama
            all_pools = await ctx.services.defillama.get_pools(
                chain=chain_type,
                min_tvl=100000,  # $100K minimum TVL
                min_apy=0.5,     # 0.5% minimum APY
            )
            
            # Filter for staking/liquid staking if asset specified
            if asset:
                asset_lower = asset.lower()
                all_pools = [p for p in all_pools if asset_lower in p.get("symbol", "").lower()]
            
            # Take top pools by APY
            all_pools.sort(key=lambda x: x.get("apy", 0) or 0, reverse=True)
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
