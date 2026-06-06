"""deBridge DLN client — implements the composed_plan.Bridge protocol.

Three concerns:
1. `DeBridgeClient.build()` — legacy convenience for cross-chain quote that
   produces an unsigned tx envelope. Kept for callers that want a single
   one-shot call (no composed-plan lifecycle).
2. `DeBridgeBridge` — `composed_plan.Bridge` implementation: `quote()` and
   `status()` so `snapshot_bridge_quote()` + `watch_for_fill()` work.
3. `parse_webhook_payload()` — webhook callback shape so the `/api/v1/
   debridge/webhook` route can resolve a pending order without polling.
"""
from __future__ import annotations

from typing import Any

import httpx

from src.config import settings

_DLN_BASE = "https://dln.debridge.finance/v1.0"


class DeBridgeClient:
    """Legacy single-shot client. Prefer DeBridgeBridge for composed plans."""

    def __init__(self) -> None:
        self._base = settings.debridge_api_base

    async def build(
        self,
        *,
        src_chain_id: int,
        dst_chain_id: int,
        token_in: str,
        token_out: str,
        amount: int,
        from_addr: str,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.post(
                f"{self._base}/order/create",
                json={
                    "srcChainId": src_chain_id,
                    "dstChainId": dst_chain_id,
                    "srcChainTokenIn": token_in,
                    "dstChainTokenOut": token_out,
                    "srcChainTokenInAmount": str(amount),
                    "senderAddress": from_addr,
                },
            )
            r.raise_for_status()
            data = r.json()
            return {
                "unsigned_tx": data.get("tx", {}),
                "estimated_seconds": data.get("estimated_seconds", 300),
                "order_id": data.get("orderId"),
            }


class DeBridgeBridge:
    """`composed_plan.Bridge` implementation against deBridge DLN."""

    name = "debridge-dln"

    def __init__(self, base: str | None = None) -> None:
        self._base = base or _DLN_BASE

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
        """Hit DLN /dln/order/quote → expected dst amount + slippage band."""
        params = {
            "srcChainId": src_chain_id,
            "srcChainTokenIn": token_in,
            "srcChainTokenInAmount": str(amount),
            "dstChainId": dst_chain_id,
            "dstChainTokenOut": token_out,
            "dstChainTokenOutRecipient": recipient,
            "prependOperatingExpenses": "true",
        }
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.get(f"{self._base}/dln/order/quote", params=params)
            r.raise_for_status()
            data = r.json()
        estimation = data.get("estimation") or {}
        _dst_out = estimation.get("dstChainTokenOut") or {}
        dst_token_amount = (
            _dst_out.get("amount")
            or _dst_out.get("recommendedAmount")
            or "0"
        )
        recommended_slippage_bps = int(
            estimation.get("recommendedSlippage", 50) * 100
            if isinstance(estimation.get("recommendedSlippage"), float)
            else estimation.get("recommendedSlippage") or 50
        )
        return {
            "expected_dst_amount": int(dst_token_amount),
            "slippage_bps_band": {
                "min": max(1, recommended_slippage_bps // 2),
                "max": recommended_slippage_bps,
            },
            "quote_id": data.get("orderId") or (data.get("estimation") or {}).get("orderId"),
            "ttl_s": int((data.get("estimation") or {}).get("orderTtlSec", 600)),
        }

    async def create_order_encoded(
        self,
        *,
        src_chain_id: int,
        dst_chain_id: int,
        token_in: str,
        token_out: str,
        amount: int,
        sender: str,
        recipient: str,
        referral_code: int = 0,
    ) -> dict[str, Any]:
        """RC7a — fetch the REAL unsigned-tx envelope from DLN.

        Hits `/dln/order/create-tx` (the production endpoint that returns
        signable calldata; docs.debridge.finance/dln/api/quick-start).
        Returns `{tx: {to, data, value, chainId}, order_id, fix_fee_quote,
        estimated_dst_amount, slippage_bps_band}`.

        Why this exists separately from `quote()`: the lifecycle-aware
        composed-plan builder needs to:
          1. snapshot the expected dst amount (`quote()`)
          2. attach a SIGNABLE bridge-leg tx (`create_order_encoded()`)
        We never bundle these because the snapshot must capture quote_id
        + slippage band even when the user hasn't decided to broadcast.

        Raises `httpx.HTTPStatusError` on 4xx/5xx; caller wraps into a
        `composed_plan_bridge_build_failed` envelope.
        """
        params = {
            "srcChainId": src_chain_id,
            "srcChainTokenIn": token_in,
            "srcChainTokenInAmount": str(amount),
            "dstChainId": dst_chain_id,
            "dstChainTokenOut": token_out,
            "dstChainTokenOutRecipient": recipient,
            "dstChainTokenOutAmount": "auto",  # solver decides; we snapshot the quote separately
            "senderAddress": sender,
            "srcChainOrderAuthorityAddress": sender,
            "dstChainOrderAuthorityAddress": recipient,
            "referralCode": referral_code,
            "prependOperatingExpenses": "true",
            "deBridgeApp": "AISentinel",
        }
        async with httpx.AsyncClient(timeout=20) as cli:
            r = await cli.get(f"{self._base}/dln/order/create-tx", params=params)
            r.raise_for_status()
            data = r.json()
        tx_blob = data.get("tx") or {}
        # DLN returns tx.{to,data,value} for EVM src and a base64
        # serialized message for Solana src. Surface both shapes; the
        # caller decides which one to attach based on chain_kind.
        return {
            "tx": tx_blob,
            "order_id": data.get("orderId") or (data.get("estimation") or {}).get("orderId"),
            "fix_fee_quote": data.get("fixFee"),
            "estimated_dst_amount": (
                ((data.get("estimation") or {}).get("dstChainTokenOut") or {}).get("amount")
                or ((data.get("estimation") or {}).get("dstChainTokenOut") or {}).get("recommendedAmount")
            ),
            "raw": data,
        }

    async def status(self, order_id: str) -> dict[str, Any]:
        """Hit DLN /dln/order/{orderId} → fill state + actual dst amount."""
        async with httpx.AsyncClient(timeout=12) as cli:
            r = await cli.get(f"{self._base}/dln/order/{order_id}")
            if r.status_code == 404:
                return {"state": "unknown"}
            r.raise_for_status()
            data = r.json()
        raw_state = (data.get("state") or "").lower()
        # DLN state vocabulary → composed_plan vocabulary.
        mapping = {
            "fulfilled": "filled",
            "claimed": "filled",
            "cancelled": "cancelled",
            "failed": "failed",
            "expired": "cancelled",
            "created": "created",
            "broadcasted": "created",
        }
        state = mapping.get(raw_state, raw_state or "unknown")
        actual = (
            (data.get("dstChainTokenOut") or {}).get("filledAmount")
            or (data.get("fulfilledOrder") or {}).get("dstAmount")
        )
        return {
            "state": state,
            "actual_dst_amount": int(actual) if actual else None,
            "raw": data,
        }


def parse_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise the DLN webhook event into the composed_plan FillResolution
    vocabulary. Webhook events include `order.fulfilled`, `order.cancelled`,
    `order.claimed`, etc.
    """
    event_type = (payload.get("event") or payload.get("type") or "").lower()
    order = payload.get("order") or payload
    order_id = order.get("orderId") or order.get("id")
    state_map = {
        "order.fulfilled": "filled",
        "order.claimed": "filled",
        "order.cancelled": "cancelled",
        "order.expired": "cancelled",
        "order.failed": "failed",
    }
    state = state_map.get(event_type, "unknown")
    actual = (
        order.get("dstChainTokenOut", {}).get("filledAmount")
        if isinstance(order.get("dstChainTokenOut"), dict)
        else None
    )
    return {
        "order_id": order_id,
        "state": state,
        "actual_dst_amount": int(actual) if actual else None,
    }
