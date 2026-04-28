from src.agent.tools._base import ok_envelope


async def build_stake_tx(ctx, *, protocol, amount, user_addr, chain_id=1):
    if hasattr(ctx.services, "stake_builder") and ctx.services.stake_builder:
        result = await ctx.services.stake_builder.build(
            protocol, amount, user_addr, chain_id
        )
    else:
        result = {"unsigned_tx": {}, "protocol": protocol, "asset": "unknown"}
    data = {
        "steps": [
            {
                "step": 1,
                "action": "stake",
                "detail": f"Stake {amount} on {protocol}",
            }
        ],
        "requires_signature": True,
    }
    return ok_envelope(data=result, card_type="stake", card_payload=data)
