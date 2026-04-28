from src.agent.tools._base import ok_envelope


async def build_bridge_tx(
    ctx,
    *,
    src_chain_id,
    dst_chain_id,
    token_in,
    token_out,
    amount,
    from_addr,
):
    if hasattr(ctx.services, "debridge") and ctx.services.debridge:
        result = await ctx.services.debridge.build(
            src_chain_id=src_chain_id,
            dst_chain_id=dst_chain_id,
            token_in=token_in,
            token_out=token_out,
            amount=amount,
            from_addr=from_addr,
        )
    else:
        result = {"unsigned_tx": {}, "estimated_seconds": 300}
    data = {
        "source_chain": str(src_chain_id),
        "target_chain": str(dst_chain_id),
        "pay": {"address": token_in, "amount": amount},
        "receive": {"address": token_out},
        "estimated_seconds": result.get("estimated_seconds", 300),
    }
    return ok_envelope(data=result, card_type="bridge", card_payload=data)
