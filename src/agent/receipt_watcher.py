from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


RpcCall = Callable[[str, list[Any]], Awaitable[Any]]
SleepFn = Callable[[float], Any]


class ReceiptWatcher:
    def __init__(self, rpc_call: RpcCall, sleep: SleepFn | None = None) -> None:
        self._rpc_call = rpc_call
        self._sleep = sleep or asyncio.sleep

    async def _sleep_once(self, seconds: float) -> None:
        maybe = self._sleep(seconds)
        if hasattr(maybe, "__await__"):
            await maybe

    async def wait_evm_receipt(self, tx_hash: str, *, max_attempts: int = 12) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(max_attempts):
            receipt = await self._rpc_call("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                return dict(receipt)
            if attempt < max_attempts - 1:
                await self._sleep_once(delay)
                delay = min(delay * 2, 300)
        raise TimeoutError(f"receipt not found for {tx_hash}")

    async def wait_solana_signature(self, signature: str, *, max_attempts: int = 12) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(max_attempts):
            response = await self._rpc_call("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])
            status = (response or {}).get("value", [None])[0]
            if status and status.get("confirmationStatus") in {"confirmed", "finalized"} and status.get("err") is None:
                return {"signature": signature, **status}
            if attempt < max_attempts - 1:
                await self._sleep_once(delay)
                delay = min(delay * 2, 300)
        raise TimeoutError(f"signature not confirmed for {signature}")
