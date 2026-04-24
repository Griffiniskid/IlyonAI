from src.agent.tools._base import ok_envelope, err_envelope


async def search_dexscreener_pairs(ctx, *, query, limit=10):
    """Search for trading pairs on DEXs using DexScreener."""
    
    if hasattr(ctx.services, "dexscreener") and ctx.services.dexscreener:
        try:
            results = await ctx.services.dexscreener.search_tokens(query, limit=limit)
            
            if results:
                return ok_envelope(
                    data={
                        "query": query,
                        "pairs": results,
                        "count": len(results),
                        "source": "DexScreener",
                    },
                    card_type="pair_list",
                    card_payload={
                        "query": query,
                        "pairs": results,
                    }
                )
        except Exception as e:
            print(f"DexScreener search error: {e}")
    
    return err_envelope(
        "search_failed",
        f"Unable to search for '{query}'. Please try again.",
        card_type="pair_list"
    )
