from src.agent.tools._base import ok_envelope


async def get_staking_options(ctx, *, chain=None, asset=None, limit=10):
    pools = []
    if hasattr(ctx.services, "opportunity") and ctx.services.opportunity:
        pools = await ctx.services.opportunity.scan(
            category=["staking", "liquid-staking"], limit=limit
        )
    if len(pools) == 1:
        data = pools[0]
        return ok_envelope(data=data, card_type="stake", card_payload=data)
    data = {
        "positions": pools,
        "total_usd": "0",
        "weighted_sentinel": 0,
        "risk_mix": {},
    }
    return ok_envelope(data=data, card_type="allocation", card_payload=data)
