"""Enso shortcuts API client.

Auth: X-API-KEY header (Authorization: Bearer is wrong and returns 401).
Rate limit: free tier = 1 req/s. We pace at 1.15s/req via a global asyncio.Lock
and time.monotonic timestamp so concurrent callers serialize.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from src.config import settings

_BASE = "https://api.enso.finance/api/v1"
_MIN_INTERVAL_S = 1.15

_pace_lock = asyncio.Lock()
_last_call_at = 0.0


async def _pace() -> None:
    global _last_call_at
    async with _pace_lock:
        now = time.monotonic()
        wait = (_last_call_at + _MIN_INTERVAL_S) - now
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_at = time.monotonic()


class EnsoClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.enso_api_key

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"X-API-KEY": self.api_key}

    async def networks(self) -> list[dict[str, Any]]:
        await _pace()
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.get(f"{_BASE}/networks", headers=self._headers())
            r.raise_for_status()
            return r.json()

    async def quote(
        self,
        *,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: str,
        from_addr: str,
        slippage_bps: int = 100,
    ) -> dict[str, Any]:
        await _pace()
        params = {
            "chainId": chain_id,
            "tokenIn": token_in,
            "tokenOut": token_out,
            "amountIn": amount_in,
            "fromAddress": from_addr,
            "slippage": slippage_bps,
        }
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.get(
                f"{_BASE}/shortcuts/quote", params=params, headers=self._headers()
            )
            r.raise_for_status()
            return r.json()

    async def route(
        self,
        *,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: str,
        from_addr: str,
        receiver: str | None = None,
        spender: str | None = None,
        slippage_bps: int = 100,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "chainId": chain_id,
            "tokenIn": token_in,
            "tokenOut": token_out,
            "amountIn": amount_in,
            "fromAddress": from_addr,
            "slippage": slippage_bps,
        }
        if receiver:
            params["receiver"] = receiver
        if spender:
            params["spender"] = spender
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            await _pace()
            async with httpx.AsyncClient(timeout=45) as cli:
                r = await cli.get(
                    f"{_BASE}/shortcuts/route", params=params, headers=self._headers()
                )
                if r.status_code == 429 and attempt < max_retries:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                try:
                    r.raise_for_status()
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    if r.status_code >= 500 and attempt < max_retries:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise
                return r.json()
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Enso route: retry budget exhausted")

    async def build(
        self,
        *,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: str,
        from_addr: str,
        slippage_bps: int = 100,
        receiver: str | None = None,
        spender: str | None = None,
    ) -> dict[str, Any]:
        """Returns shape: {"unsigned_tx": {...}, "simulation": {...}, "raw": full_body}."""
        body = await self.route(
            chain_id=chain_id,
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            from_addr=from_addr,
            receiver=receiver,
            spender=spender,
            slippage_bps=slippage_bps,
        )
        tx = body.get("tx") or {}
        return {
            "unsigned_tx": {
                "to": tx.get("to"),
                "data": tx.get("data"),
                "value": tx.get("value", "0x0"),
                "from": tx.get("from"),
                "gas": body.get("gas"),
            },
            "simulation": {
                "ok": True,
                "chain_id": chain_id,
                "amount_out": body.get("amountOut"),
                "price_impact_bps": body.get("priceImpact"),
                "route": body.get("route"),
            },
            "raw": body,
        }
