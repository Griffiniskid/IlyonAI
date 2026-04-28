import httpx
from src.config import settings


class JupiterClient:
    def __init__(self):
        self._base = settings.jupiter_api_base

    async def quote(self, input_mint, output_mint, amount, slippage_bps=50):
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.get(
                f"{self._base}/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": amount,
                    "slippageBps": slippage_bps,
                },
            )
            r.raise_for_status()
            return r.json()

    async def build(self, quote_response, user_public_key):
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.post(
                f"{self._base}/swap",
                json={
                    "quoteResponse": quote_response,
                    "userPublicKey": user_public_key,
                },
            )
            r.raise_for_status()
            return r.json()  # contains swapTransaction (base64)
