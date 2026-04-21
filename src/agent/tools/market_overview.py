from src.agent.tools._base import ok_envelope


async def get_defi_market_overview(ctx, *, category=None, limit=20):
    protocols = []
    if hasattr(ctx.services, "defillama") and ctx.services.defillama:
        protocols = await ctx.services.defillama.protocols(limit=limit)
    data = {"protocols": protocols}
    return ok_envelope(data=data, card_type="market_overview", card_payload=data)
