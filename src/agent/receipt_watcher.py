from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from src.config import settings


RpcCall = Callable[[str, list[Any]], Awaitable[Any]]
SleepFn = Callable[[float], Any]

# Common EVM event signatures
_EVENT_SIGNATURES = {
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": "Transfer(address,address,uint256)",
    "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925": "Approval(address,address,uint256)",
    "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c": "Deposit(address,uint256)",
    "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65": "Withdrawal(address,uint256)",
}


class ReceiptWatcher:
    def __init__(
        self,
        rpc_call: RpcCall,
        sol_rpc_call: RpcCall | None = None,
        sleep: SleepFn | None = None,
    ) -> None:
        self._rpc_call = rpc_call
        self._sol_rpc_call = sol_rpc_call or rpc_call
        self._sleep = sleep or asyncio.sleep
        self._base_url = settings.SENTINEL_API_TARGET or "http://localhost:8080"

    async def _sleep_once(self, seconds: float) -> None:
        maybe = self._sleep(seconds)
        if hasattr(maybe, "__await__"):
            await maybe

    async def wait_evm_receipt(self, tx_hash: str, *, max_attempts: int = 12) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(max_attempts):
            receipt = await self._rpc_call("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                result = dict(receipt)
                result["decoded_logs"] = self._decode_logs(result.get("logs", []))
                return result
            if attempt < max_attempts - 1:
                await self._sleep_once(delay)
                delay = min(delay * 2, 300)
        raise TimeoutError(f"receipt not found for {tx_hash}")

    async def wait_solana_signature(self, signature: str, *, max_attempts: int = 12) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(max_attempts):
            response = await self._sol_rpc_call(
                "getSignatureStatuses", [[signature], {"searchTransactionHistory": True}]
            )
            status = (response or {}).get("value", [None])[0]
            if status and status.get("confirmationStatus") in {"confirmed", "finalized"} and status.get("err") is None:
                return {"signature": signature, **status}
            if attempt < max_attempts - 1:
                await self._sleep_once(delay)
                delay = min(delay * 2, 300)
        raise TimeoutError(f"signature not confirmed for {signature}")

    @staticmethod
    def decode_log(log: dict[str, Any]) -> dict[str, Any]:
        topics = log.get("topics", [])
        topic0 = topics[0] if topics else None
        data = log.get("data", "0x")
        address = log.get("address", "")

        if not topic0:
            return {
                "address": address,
                "event_signature": "unknown",
                "topic0": None,
                "raw_topics": topics,
                "raw_data": data,
            }

        event_signature = _EVENT_SIGNATURES.get(topic0, "unknown")
        decoded: dict[str, Any] = {
            "address": address,
            "event_signature": event_signature,
            "topic0": topic0,
        }

        def _fmt_addr(topic: str) -> str:
            return "0x" + topic[2:].lstrip("0")

        if event_signature == "Transfer(address,address,uint256)" and len(topics) >= 3:
            decoded["from"] = _fmt_addr(topics[1])
            decoded["to"] = _fmt_addr(topics[2])
            decoded["value"] = str(int(data, 16)) if data and data != "0x" else "0"
        elif event_signature == "Approval(address,address,uint256)" and len(topics) >= 3:
            decoded["owner"] = _fmt_addr(topics[1])
            decoded["spender"] = _fmt_addr(topics[2])
            decoded["value"] = str(int(data, 16)) if data and data != "0x" else "0"
        else:
            decoded["raw_topics"] = topics
            decoded["raw_data"] = data

        return decoded

    @classmethod
    def _decode_logs(cls, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [cls.decode_log(log) for log in logs]

    @classmethod
    def from_settings(cls) -> ReceiptWatcher:
        base_url = settings.SENTINEL_API_TARGET or "http://localhost:8080"

        async def _rpc_call(method: str, params: list[Any]) -> Any:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/v1/rpc-proxy",
                    json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                ) as resp:
                    result = await resp.json()
                    return result.get("result")

        async def _sol_rpc_call(method: str, params: list[Any]) -> Any:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/v1/solana-rpc-proxy",
                    json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                ) as resp:
                    result = await resp.json()
                    return result.get("result")

        watcher = cls(rpc_call=_rpc_call, sol_rpc_call=_sol_rpc_call)
        watcher._base_url = base_url
        return watcher
