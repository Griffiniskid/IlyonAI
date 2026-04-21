from src.routing.enso_client import EnsoClient
from src.routing.jupiter_client import JupiterClient

CHAIN_FAMILIES = {
    "ethereum",
    "base",
    "arbitrum",
    "bsc",
    "polygon",
    "optimism",
    "avalanche",
}


class QuoteService:
    def __init__(self):
        self.enso = EnsoClient()
        self.jupiter = JupiterClient()

    async def quote(self, chain, token_in, token_out, amount):
        if chain in CHAIN_FAMILIES or chain.isdigit():
            chain_id = (
                int(chain)
                if chain.isdigit()
                else {
                    "ethereum": 1,
                    "base": 8453,
                    "arbitrum": 42161,
                    "bsc": 56,
                    "polygon": 137,
                    "optimism": 10,
                    "avalanche": 43114,
                }[chain]
            )
            r = await self.enso.build(
                chain_id=chain_id,
                token_in=token_in,
                token_out=token_out,
                amount_in=amount,
                from_addr="0x0",
            )
            return {
                "pay": {"address": token_in, "amount": amount},
                "receive": {"address": token_out},
                "rate": "0",
                "router": "enso",
                "price_impact_pct": 0.0,
            }
        else:
            r = await self.jupiter.quote(token_in, token_out, amount)
            return {
                "pay": r.get("inputMint"),
                "receive": r.get("outputMint"),
                "rate": r.get("outAmount"),
                "router": "jupiter",
                "price_impact_pct": float(r.get("priceImpactPct", 0)),
            }
