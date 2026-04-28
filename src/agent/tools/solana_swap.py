from src.agent.tools._base import ok_envelope


async def build_solana_swap(
    ctx,
    *,
    input_mint,
    output_mint,
    amount,
    user_public_key,
    slippage_bps=50,
):
    if hasattr(ctx.services, "jupiter") and ctx.services.jupiter:
        quote = await ctx.services.jupiter.quote(
            input_mint, output_mint, amount, slippage_bps
        )
        result = await ctx.services.jupiter.build(quote, user_public_key)
    else:
        result = {"swapTransaction": "", "unsigned": True}
    return ok_envelope(
        data=result,
        card_type="swap_quote",
        card_payload={
            "pay": {"address": input_mint},
            "receive": {"address": output_mint},
            "rate": "0",
            "router": "jupiter",
            "price_impact_pct": 0.0,
        },
    )
