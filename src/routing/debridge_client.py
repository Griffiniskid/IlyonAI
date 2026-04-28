import httpx
from src.config import settings


class DeBridgeClient:
    def __init__(self):
        self._base = settings.debridge_api_base

    async def build(
        self,
        *,
        src_chain_id,
        dst_chain_id,
        token_in,
        token_out,
        amount,
        from_addr,
    ):
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.post(
                f"{self._base}/order/create",
                json={
                    "srcChainId": src_chain_id,
                    "dstChainId": dst_chain_id,
                    "srcChainTokenIn": token_in,
                    "dstChainTokenOut": token_out,
                    "srcChainTokenInAmount": amount,
                    "senderAddress": from_addr,
                },
            )
            r.raise_for_status()
            data = r.json()
            return {
                "unsigned_tx": data.get("tx", {}),
                "estimated_seconds": data.get("estimated_seconds", 300),
            }
