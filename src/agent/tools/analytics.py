from src.agent.tools._base import ok_envelope


async def get_defi_analytics(
    ctx, *, query=None, protocol=None, asset=None, pool_id=None, chain=None
):
    if pool_id or (protocol and asset):
        data = {
            "protocol": protocol or "unknown",
            "asset": asset or "unknown",
            "chain": chain or "ethereum",
        }
        return ok_envelope(data=data, card_type="pool", card_payload=data)
    data = {"protocols": [], "query": query}
    return ok_envelope(data=data, card_type="market_overview", card_payload=data)
