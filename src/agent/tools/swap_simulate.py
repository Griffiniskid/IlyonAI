from src.agent.tools._base import ok_envelope


async def simulate_swap(ctx, *, chain, token_in, token_out, amount):
    data = {
        "pay": {"address": token_in, "amount": amount},
        "receive": {"address": token_out, "amount": "0"},
        "rate": "0",
        "router": "auto",
        "price_impact_pct": 0.0,
    }
    if hasattr(ctx.services, "quote") and ctx.services.quote:
        data = await ctx.services.quote.quote(chain, token_in, token_out, amount)
    return ok_envelope(data=data, card_type="swap_quote", card_payload=data)
