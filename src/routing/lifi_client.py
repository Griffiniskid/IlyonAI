"""LI.FI bridge client — implements the composed_plan.Bridge protocol.

LI.FI aggregates 25+ bridges (Across, Hop, cBridge, Stargate, Wormhole,
Connext, etc.) behind a single quote API. Used as the deBridge fallback
when DLN refuses a route.

Public endpoints (no auth required for read; sign-in via JWT for write):
  GET https://li.quest/v1/quote
  GET https://li.quest/v1/status

Reference: https://docs.li.fi/li.fi-api
"""
from __future__ import annotations

from typing import Any

import httpx


_LIFI_BASE = "https://li.quest/v1"


class LifiBridge:
    """`composed_plan.Bridge` implementation against LI.FI aggregator."""

    name = "lifi"

    def __init__(self, base: str | None = None, http: Any = None) -> None:
        self._base = base or _LIFI_BASE
        # `http` is injected for tests; production uses httpx.AsyncClient.
        self._http = http

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
        """LI.FI /v1/quote → expected toAmount + min toAmountMin + tool id.

        Returns dict matching the Bridge protocol contract:
          {expected_dst_amount, slippage_bps_band, quote_id, ttl_s}
        """
        params = {
            "fromChain": src_chain_id,
            "toChain": dst_chain_id,
            "fromToken": token_in,
            "toToken": token_out,
            "fromAmount": str(amount),
            "fromAddress": recipient,
            "toAddress": recipient,
            "slippage": "0.005",  # 50 bps default; caller can re-quote with tighter
        }
        owned = self._http is None
        cli = await self._client()
        try:
            r = await cli.get(f"{self._base}/quote", params=params)
            r.raise_for_status()
            data = r.json()
        finally:
            if owned:
                await cli.aclose()

        estimate = data.get("estimate") or {}
        to_amount = int(estimate.get("toAmount") or 0)
        to_amount_min = int(estimate.get("toAmountMin") or to_amount)
        # Slippage band from the actual quote tolerance.
        if to_amount > 0:
            band_max_bps = max(
                0, int(round((1.0 - (to_amount_min / to_amount)) * 10_000))
            )
        else:
            band_max_bps = 50
        tool = data.get("tool") or "lifi"
        return {
            "expected_dst_amount": to_amount,
            "slippage_bps_band": {"min": 0, "max": band_max_bps},
            "quote_id": data.get("id") or tool,
            "ttl_s": int(estimate.get("executionDuration") or 600),
            "via": tool,
            "raw": data,
        }

    async def status(self, order_id: str) -> dict[str, Any]:
        """LI.FI /v1/status?txHash=… → state + actualToAmount when available."""
        params = {"txHash": order_id}
        owned = self._http is None
        cli = await self._client()
        try:
            r = await cli.get(f"{self._base}/status", params=params)
            r.raise_for_status()
            data = r.json()
        finally:
            if owned:
                await cli.aclose()

        # LI.FI status strings: NOT_FOUND / PENDING / DONE / FAILED / INVALID
        raw_status = (data.get("status") or "").upper()
        state_map = {
            "DONE": "filled",
            "FAILED": "failed",
            "INVALID": "failed",
            "PENDING": "created",
            "NOT_FOUND": "created",
        }
        state = state_map.get(raw_status, "created")
        receiving = data.get("receiving") or {}
        actual = receiving.get("amount")
        return {
            "state": state,
            "actual_dst_amount": int(actual) if actual is not None else None,
            "raw": data,
        }
