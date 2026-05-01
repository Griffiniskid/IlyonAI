from src.agent.tools.wallet_bridge import build_bridge_tx


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
    return await build_bridge_tx(
        ctx,
        src_chain_id=src_chain_id,
        dst_chain_id=dst_chain_id,
        token_in=token_in,
        token_out=token_out,
        amount=amount,
        from_addr=from_addr,
    )
