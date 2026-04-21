from src.agent.tools._base import ToolCtx, ok_envelope, err_envelope


async def get_wallet_balance(ctx: ToolCtx, *, wallet=None):
    addr = wallet or ctx.wallet
    if not addr:
        return err_envelope("missing_wallet", "No wallet address provided")
    data = {"wallet": addr, "total_usd": "0.00", "by_chain": {}}
    if hasattr(ctx.services, "portfolio") and ctx.services.portfolio:
        data = await ctx.services.portfolio.aggregate(addr)
    return ok_envelope(data=data, card_type="balance", card_payload=data)
