from src.agent.tools._base import ok_envelope


async def find_liquidity_pool(ctx, *, protocol=None, asset=None, chain=None):
    data = {
        "protocol": protocol or "unknown",
        "asset": asset or "unknown",
        "chain": chain or "ethereum",
        "apy": "0%",
        "tvl": "$0",
    }
    return ok_envelope(data=data, card_type="pool", card_payload=data)
