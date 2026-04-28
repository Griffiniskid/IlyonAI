import httpx
from src.config import settings


class EnsoClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or settings.enso_api_key
        self._base = "https://api.enso.finance/api/v1"

    async def build(self, *, chain_id, token_in, token_out, amount_in, from_addr):
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.post(
                f"{self._base}/shortcuts/route",
                json={
                    "chainId": chain_id,
                    "tokenIn": token_in,
                    "tokenOut": token_out,
                    "amountIn": amount_in,
                    "fromAddress": from_addr,
                },
                headers={"Authorization": f"Bearer {self.api_key}"}
                if self.api_key
                else {},
            )
            r.raise_for_status()
            tx = r.json().get("tx", {})
            return {
                "unsigned_tx": tx,
                "simulation": {"ok": True, "chain_id": chain_id},
            }
