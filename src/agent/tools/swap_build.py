from src.agent.tools._base import ok_envelope


async def build_swap_tx(
    ctx, *, chain_id, token_in, token_out, amount_in, from_addr
):
    if hasattr(ctx.services, "enso") and ctx.services.enso:
        result = await ctx.services.enso.build(
            chain_id=chain_id,
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            from_addr=from_addr,
        )
    else:
        result = {
            "unsigned_tx": {},
            "simulation": {"ok": True, "chain_id": chain_id},
        }
    return ok_envelope(
        data=result,
        card_type="swap_quote",
        card_payload={
            "pay": {"address": token_in},
            "receive": {"address": token_out},
            "rate": "0",
            "router": "enso",
            "price_impact_pct": 0.0,
        },
    )
