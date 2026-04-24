from src.agent.tools._base import ok_envelope, err_envelope


_CHAIN_ALIAS = {
    "eth": "ethereum", "ethereum": "ethereum", "mainnet": "ethereum",
    "arb": "arbitrum", "arbitrum": "arbitrum",
    "op": "optimism", "optimism": "optimism",
    "bsc": "bsc", "binance": "bsc", "bnb": "bsc",
    "polygon": "polygon", "matic": "polygon",
    "base": "base",
    "avax": "avalanche", "avalanche": "avalanche",
    "sol": "solana", "solana": "solana",
}


def _match_chain(record_chain: str, wanted: str | None) -> bool:
    if not wanted:
        return True
    wanted_norm = _CHAIN_ALIAS.get(wanted.lower(), wanted.lower())
    rc = (record_chain or "").lower().replace(" ", "")
    return rc == wanted_norm


async def find_liquidity_pool(ctx, *, token_a, token_b, chain=None):
    """Find liquidity pools for a token pair using real data.

    Strategy:
        1. DefiLlama yield pool universe — best for canonical pools with
           chain, APY, TVL (Uniswap V3 USDC/WETH, etc).
        2. DexScreener fallback for DEX-native / long-tail pairs.
    """

    # Try DefiLlama FIRST — it has canonical chain-scoped pool records.
    if hasattr(ctx.services, "defillama") and ctx.services.defillama:
        try:
            from src.chains.base import ChainType

            chain_map = {
                "ethereum": ChainType.ETHEREUM,
                "arbitrum": ChainType.ARBITRUM,
                "optimism": ChainType.OPTIMISM,
                "polygon": ChainType.POLYGON,
                "bsc": ChainType.BSC,
                "base": ChainType.BASE,
                "avalanche": ChainType.AVALANCHE,
                "solana": ChainType.SOLANA,
            }
            wanted_chain_str = _CHAIN_ALIAS.get((chain or "").lower(), (chain or "").lower()) if chain else None
            chain_type = chain_map.get(wanted_chain_str) if wanted_chain_str else None

            dl_pools = await ctx.services.defillama.get_pools(
                chain=chain_type,
                min_tvl=1_000_000,
            )
            # Match pools where the pool symbol contains both tokens.
            def _pair_hit(sym: str) -> bool:
                s = (sym or "").upper()
                return (token_a.upper() in s) and (token_b.upper() in s)

            matches = [p for p in dl_pools if _pair_hit(p.get("symbol", ""))]
            matches.sort(key=lambda p: p.get("tvlUsd", 0) or 0, reverse=True)
            matches = matches[:5]

            if matches:
                pools = []
                for p in matches:
                    pools.append({
                        "token_a": token_a,
                        "token_b": token_b,
                        "dex": p.get("project", "unknown"),
                        "chain": p.get("chain", chain or "unknown"),
                        "liquidity_usd": p.get("tvlUsd", 0),
                        "apy": p.get("apy", 0),
                        "pair_address": p.get("pool", ""),
                        "symbol": p.get("symbol", ""),
                    })
                return ok_envelope(
                    data={
                        "token_a": token_a,
                        "token_b": token_b,
                        "pools": pools,
                        "count": len(pools),
                        "source": "DefiLlama",
                        "chain_requested": chain,
                    },
                    card_type="pool",
                    card_payload={
                        "protocol": pools[0].get("dex", "Unknown"),
                        "chain": str(pools[0].get("chain", "Unknown")),
                        "asset": f"{token_a}/{token_b}",
                        "apy": f"{float(pools[0].get('apy', 0) or 0):.2f}%",
                        "tvl": f"${float(pools[0].get('liquidity_usd', 0) or 0):,.0f}",
                    },
                )
        except Exception as e:
            print(f"DefiLlama pool error: {e}")

    # DexScreener fallback
    if hasattr(ctx.services, "dexscreener") and ctx.services.dexscreener:
        try:
            query = f"{token_a} {token_b}"
            wanted_chain = _CHAIN_ALIAS.get((chain or "").lower(), chain or None) if chain else None
            results = await ctx.services.dexscreener.search_tokens(
                query, limit=50, chain=wanted_chain
            )

            if results:
                # Filter by requested chain
                filtered = [r for r in results if _match_chain(r.get("chain", ""), chain)]
                # If the chain filter drops everything, fall back to all results.
                chosen = filtered or results
                # Prefer deepest liquidity
                chosen.sort(key=lambda x: float(x.get("liquidity", 0) or 0), reverse=True)
                chosen = chosen[:5]
                pools = []
                for r in chosen:
                    pools.append({
                        "token_a": token_a,
                        "token_b": token_b,
                        "dex": r.get("dex", "unknown"),
                        "chain": r.get("chain", chain or "unknown"),
                        "liquidity_usd": r.get("liquidity", 0),
                        "price_usd": r.get("priceUsd", 0),
                        "pair_address": r.get("pair_address", ""),
                    })

                return ok_envelope(
                    data={
                        "token_a": token_a,
                        "token_b": token_b,
                        "pools": pools,
                        "count": len(pools),
                        "source": "DexScreener",
                        "chain_requested": chain,
                    },
                    card_type="pool",
                    card_payload={
                        "protocol": pools[0].get("dex", "Unknown"),
                        "chain": pools[0].get("chain", "Unknown"),
                        "asset": f"{token_a}/{token_b}",
                        "apy": "N/A",
                        "tvl": f"${float(pools[0].get('liquidity_usd', 0) or 0):,.0f}",
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
