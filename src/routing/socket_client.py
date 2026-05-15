"""Socket bridge client — implements the composed_plan.Bridge protocol.

Socket (formerly Bungee) aggregates Hop, Stargate, Polygon, Across,
Hyphen, Symbiosis, Connext, cBridge, Anyswap, Wormhole, and several
others. Used as a third-tier fallback when both deBridge DLN and LI.FI
refuse a route.

Public endpoints (API-KEY header required for higher rate limits;
read access works without auth at lower QPS):
  GET https://api.socket.tech/v2/quote
  GET https://api.socket.tech/v2/bridge-status

Reference: https://docs.socket.tech/
"""
from __future__ import annotations

from typing import Any

import httpx

from src.config import settings


_SOCKET_BASE = "https://api.socket.tech/v2"


class SocketBridge:
    """`composed_plan.Bridge` implementation against Socket aggregator."""

    name = "socket"

    def __init__(
        self,
        base: str | None = None,
        api_key: str | None = None,
        http: Any = None,
    ) -> None:
        self._base = base or _SOCKET_BASE
        self._api_key = api_key or getattr(settings, "socket_api_key", None) or ""
        self._http = http

    def _headers(self) -> dict[str, str]:
        if self._api_key:
            return {"API-KEY": self._api_key}
        return {}

    async def _client(self) -> httpx.AsyncClient:
        return self._http or httpx.AsyncClient(timeout=30)

    async def quote(
        self,
        *,
        src_chain_id: int,
        dst_chain_id: int,
        token_in: str,
        token_out: str,
        amount: int,
        recipient: str,
    ) -> dict[str, Any]:
        """Socket /v2/quote → bestRoute with userTxs + toAmount."""
        params = {
            "fromChainId": src_chain_id,
            "toChainId": dst_chain_id,
            "fromTokenAddress": token_in,
            "toTokenAddress": token_out,
            "fromAmount": str(amount),
            "userAddress": recipient,
            "recipient": recipient,
            "uniqueRoutesPerBridge": "true",
            "sort": "output",
            "singleTxOnly": "true",
        }
        owned = self._http is None
        cli = await self._client()
        try:
            r = await cli.get(
                f"{self._base}/quote", params=params, headers=self._headers()
            )
            r.raise_for_status()
            payload = r.json()
        finally:
            if owned:
                await cli.aclose()

        result = (payload or {}).get("result") or {}
        routes = result.get("routes") or []
        if not routes:
            return {
                "expected_dst_amount": 0,
                "slippage_bps_band": {"min": 0, "max": 50},
                "quote_id": None,
                "ttl_s": 600,
                "via": "socket",
                "raw": payload,
            }
        best = routes[0]
        to_amount = int(best.get("toAmount") or 0)
        # Socket returns "outputValueInUsd" and "fromAmount"; compute slippage
        # from any "minimumGasBalances"/"maxServiceTime" if exposed, else
        # default to 50 bps band.
        return {
            "expected_dst_amount": to_amount,
            "slippage_bps_band": {"min": 0, "max": 50},
            "quote_id": best.get("routeId") or best.get("routeHash"),
            "ttl_s": int(best.get("serviceTime") or 600),
            "via": best.get("usedBridgeNames", ["socket"])[0],
            "raw": payload,
        }

    async def status(self, order_id: str) -> dict[str, Any]:
        """Socket /v2/bridge-status → status + destTxHash + receivedAmount."""
        params = {"transactionHash": order_id}
        owned = self._http is None
        cli = await self._client()
        try:
            r = await cli.get(
                f"{self._base}/bridge-status",
                params=params,
                headers=self._headers(),
            )
            r.raise_for_status()
            payload = r.json()
        finally:
            if owned:
                await cli.aclose()

        result = (payload or {}).get("result") or {}
        raw_status = (result.get("destinationTxStatus") or "").upper()
        state_map = {
            "COMPLETED": "filled",
            "FAILED": "failed",
            "PENDING": "created",
            "NOT_FOUND": "created",
        }
        state = state_map.get(raw_status, "created")
        received = result.get("destinationTokenAmount")
        return {
            "state": state,
            "actual_dst_amount": int(received) if received is not None else None,
            "raw": payload,
        }
