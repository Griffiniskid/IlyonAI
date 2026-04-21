from src.agent.tools._base import ok_envelope


async def get_token_price(ctx, *, token, chain="ethereum"):
    data = {
        "symbol": token.upper(),
        "address": token,
        "chain": chain,
        "price_usd": "0",
        "change_24h_pct": 0.0,
    }
    if hasattr(ctx.services, "price") and ctx.services.price:
        data = await ctx.services.price.get(token, chain)
    return ok_envelope(data=data, card_type="token", card_payload=data)
