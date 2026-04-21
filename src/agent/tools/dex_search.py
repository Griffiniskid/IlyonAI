from src.agent.tools._base import ok_envelope


async def search_dexscreener_pairs(ctx, *, query, limit=10):
    pairs = []
    if hasattr(ctx.services, "dexscreener") and ctx.services.dexscreener:
        pairs = await ctx.services.dexscreener.search(query, limit=limit)
    data = {"query": query, "pairs": pairs}
    return ok_envelope(data=data, card_type="pair_list", card_payload=data)
