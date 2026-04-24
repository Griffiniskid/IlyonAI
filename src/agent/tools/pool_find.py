from src.agent.tools._base import ok_envelope, err_envelope


async def find_liquidity_pool(ctx, *, token_a, token_b, chain=None):
    """Find liquidity pools for a token pair using real data."""
    
    # Try DexScreener first
    if hasattr(ctx.services, "dexscreener") and ctx.services.dexscreener:
        try:
            query = f"{token_a} {token_b}"
            results = await ctx.services.dexscreener.search_tokens(query, limit=5)
            
            if results:
                pools = []
                for r in results:
                    pools.append({
                        "token_a": token_a,
                        "token_b": token_b,
                        "dex": r.get("dex", "unknown"),
                        "chain": r.get("chain", chain or "unknown"),
                        "liquidity_usd": r.get("liquidity", 0),
                        "price_usd": r.get("priceUsd", 0),
                    })
                
                return ok_envelope(
                    data={
                        "token_a": token_a,
                        "token_b": token_b,
                        "pools": pools,
                        "count": len(pools),
                        "source": "DexScreener",
                    },
                    card_type="pool",
                    card_payload={
                        "protocol": pools[0].get("dex", "Unknown"),
                        "chain": pools[0].get("chain", "Unknown"),
                        "asset": f"{token_a}/{token_b}",
                        "apy": "N/A",
                        "tvl": f"${pools[0].get('liquidity_usd', 0):,.0f}",
                    }
                )
        except Exception as e:
            print(f"DexScreener pool error: {e}")
    
    # Fallback to DefiLlama
    if hasattr(ctx.services, "defillama") and ctx.services.defillama:
        try:
            from src.chains.base import ChainType
            chain_type = None
            if chain:
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
            
            pools = await ctx.services.defillama.get_pools(
                chain=chain_type,
                min_tvl=10000,
            )
            
            # Filter for pools containing both tokens
            symbol_filter = f"{token_a}-{token_b}"
            matching = [p for p in pools if symbol_filter.lower() in p.get("symbol", "").lower()]
            
            if matching:
                pool = matching[0]
                return ok_envelope(
                    data={
                        "token_a": token_a,
                        "token_b": token_b,
                        "pool": pool,
                        "source": "DefiLlama",
                    },
                    card_type="pool",
                    card_payload={
                        "protocol": pool.get("project", "Unknown"),
                        "chain": pool.get("chain", "Unknown"),
                        "asset": pool.get("symbol", f"{token_a}/{token_b}"),
                        "apy": f"{pool.get('apy', 0):.2f}%",
                        "tvl": f"${pool.get('tvlUsd', 0):,.0f}",
                    }
                )
        except Exception as e:
            print(f"DefiLlama pool error: {e}")
    
    return err_envelope(
        "pool_not_found",
        f"No liquidity pools found for {token_a}/{token_b}. The pair may not exist yet.",
        card_type="pool"
    )
