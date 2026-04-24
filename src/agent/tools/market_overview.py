from src.agent.tools._base import ok_envelope, err_envelope


async def get_defi_market_overview(ctx, *, category=None, limit=20):
    """Get real DeFi market overview from DefiLlama."""
    protocols = []
    
    if hasattr(ctx.services, "defillama") and ctx.services.defillama:
        try:
            all_protocols = await ctx.services.defillama.get_protocols()
            
            # Sort by TVL
            all_protocols.sort(key=lambda x: x.get("tvl", 0) or 0, reverse=True)
            
            # Take top protocols
            top_protocols = all_protocols[:limit]
            
            for p in top_protocols:
                protocols.append({
                    "name": p.get("name", "Unknown"),
                    "slug": p.get("slug", ""),
                    "tvl": p.get("tvl", 0),
                    "chain_tvls": p.get("chainTvls", {}),
                    "category": p.get("category", "Unknown"),
                    "change_1d": p.get("change_1d", 0),
                    "change_7d": p.get("change_7d", 0),
                })
            
        except Exception as e:
            print(f"DefiLlama market overview error: {e}")
    
    if protocols:
        total_tvl = sum(p.get("tvl", 0) or 0 for p in protocols)
        data = {
            "protocols": protocols,
            "total_protocols": len(protocols),
            "total_tvl": total_tvl,
            "source": "DefiLlama",
        }
        return ok_envelope(data=data, card_type="market_overview", card_payload=data)
    
    return err_envelope(
        "no_market_data",
        "Unable to fetch DeFi market data. Please try again later.",
        card_type="market_overview"
    )
