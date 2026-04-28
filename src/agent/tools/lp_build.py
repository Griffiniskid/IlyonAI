from src.agent.tools._base import ok_envelope


async def build_deposit_lp_tx(
    ctx,
    *,
    protocol,
    token_a,
    token_b,
    amount_a,
    amount_b,
    user_addr,
    chain_id=1,
):
    if hasattr(ctx.services, "lp_builder") and ctx.services.lp_builder:
        result = await ctx.services.lp_builder.build(
            protocol, token_a, token_b, amount_a, amount_b, user_addr, chain_id
        )
    else:
        result = {"unsigned_tx": {}, "protocol": protocol}
    data = {
        "steps": [
            {
                "step": 1,
                "action": "deposit_lp",
                "detail": f"Deposit {amount_a}/{amount_b} on {protocol}",
            }
        ],
        "requires_signature": True,
    }
    return ok_envelope(data=result, card_type="plan", card_payload=data)
