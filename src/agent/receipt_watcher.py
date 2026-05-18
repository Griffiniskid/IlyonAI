from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from src.config import settings


RpcCall = Callable[[str, list[Any]], Awaitable[Any]]
SleepFn = Callable[[float], Any]


# Spec §6g — per-(protocol, action) → ReceiptKind mapping consumed by the
# receipt-verify wire-in. When the watcher confirms a tx, look up the
# expected receipt kind here and run verify_receipt() against the on-chain
# state. Matches the kinds in src/defi/verification/receipt_table.py.
_RECEIPT_KIND_BY_PROTOCOL_ACTION: dict[tuple[str, str], str] = {
    # Aave V3
    ("aave-v3", "supply"): "ATOKEN",
    ("aave-v3", "lend"): "ATOKEN",
    ("aave-v3", "deposit"): "ATOKEN",
    # Compound V3
    ("compound-v3", "supply"): "CTOKEN",
    ("compound-v3", "deposit"): "CTOKEN",
    # Uniswap V3 NFT
    ("uniswap-v3", "deposit_lp"): "V3_NFT",
    ("uniswap-v3", "add_liquidity"): "V3_NFT",
    ("pancakeswap-v3", "deposit_lp"): "V3_NFT",
    ("aerodrome-slipstream", "deposit_lp"): "V3_NFT",
    ("velodrome-cl", "deposit_lp"): "V3_NFT",
    # Uniswap V4
    ("uniswap-v4", "deposit_lp"): "V4_NFT",
    ("uniswap-v4", "add_liquidity"): "V4_NFT",
    # ERC-4626 vaults
    ("yearn-finance", "supply"): "ERC4626_SHARE",
    ("morpho-blue", "supply"): "ERC4626_SHARE",
    ("spark", "supply"): "ERC4626_SHARE",
    # LSTs (rebasing or share-priced ERC20)
    ("lido", "stake"): "LST_ERC20",
    ("rocket-pool", "stake"): "LST_ERC20",
    ("ether.fi", "stake"): "LST_ERC20",
    ("frax-ether", "stake"): "LST_ERC20",
    ("mantle", "stake"): "LST_ERC20",
    # LRTs (EigenLayer-restaked baskets)
    ("renzo", "stake"): "LRT_ERC20",
    ("kelp", "stake"): "LRT_ERC20",
    ("swell", "stake"): "LRT_ERC20",
    ("puffer", "stake"): "LRT_ERC20",
    # Curve / Balancer LP
    ("curve", "deposit_lp"): "LP_ERC20",
    ("balancer-v2", "deposit_lp"): "BPT",
    ("balancer-v3", "deposit_lp"): "BPT",
    # Solana CLMM / DLMM
    ("orca", "deposit_lp"): "POSITION_PDA_WITH_NFT",
    ("orca-whirlpool", "deposit_lp"): "POSITION_PDA_WITH_NFT",
    ("raydium-clmm", "deposit_lp"): "POSITION_PDA_WITH_NFT",
    ("meteora-dlmm", "deposit_lp"): "POSITION_PDA",
    # Solana AMM LP
    ("raydium-amm-v4", "deposit_lp"): "LP_MINT_SPL",
    ("raydium-cpmm", "deposit_lp"): "LP_MINT_SPL",
    ("orca-v1", "deposit_lp"): "LP_MINT_SPL",
    # Solana LSTs
    ("marinade", "stake"): "MSOL",
    ("jito", "stake"): "JITOSOL",
    ("sanctum-infinity", "stake"): "INF",
    ("sanctum", "stake"): "INF",
    # Misc
    ("kamino", "deposit_lp"): "KTOKEN",
    ("kamino-lend", "supply"): "OBLIGATION_STATE",
    ("jupiter-perps", "deposit_lp"): "JLP",
    ("pendle-v2", "add_liquidity"): "PENDLE_PT_YT",
    ("pendle-v2", "mint_py"): "PENDLE_PT_YT",
    ("pendle-v2", "redeem_py"): "PENDLE_PT_YT",
    ("pendle-v2", "swap_for_pt"): "PENDLE_PT_YT",
    ("pendle-v2", "swap_pt_for_token"): "PENDLE_PT_YT",
    ("stargate", "deposit_lp"): "STARGATE_SHARE",
}


def resolve_receipt_kind(protocol: str | None, action: str | None) -> str | None:
    """Return the ReceiptKind name for a (protocol, action) tuple, or None
    when no spec is registered."""
    if not protocol or not action:
        return None
    return _RECEIPT_KIND_BY_PROTOCOL_ACTION.get(
        (protocol.lower(), action.lower())
    )

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
                # Phase D: when the tx is a deBridge DLN bridge submission,
                # extract the orderId from logs so pending_plans can rekey
                # the placeholder quote_id with the real order_id.
                try:
                    from src.agent.debridge_order_extractor import extract_order_id_from_logs
                    chain_id_raw = result.get("chainId") or result.get("chain_id")
                    if chain_id_raw is not None:
                        chain_id = int(chain_id_raw, 16) if isinstance(chain_id_raw, str) else int(chain_id_raw)
                        order_id = extract_order_id_from_logs(chain_id, result.get("logs", []))
                        if order_id:
                            result["debridge_order_id"] = order_id
                except Exception:
                    # Best-effort; never block receipt return.
                    pass
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

    async def verify_step_receipt(
        self,
        *,
        protocol: str,
        action: str,
        chain: str,
        owner: str,
        expected: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Spec §6g — after broadcast confirms, look up the receipt kind
        for this (protocol, action) and run the per-kind verifier from
        src/defi/verification/receipt_reader.py.

        Returns the ReadResult.to_dict() shape: { confirmed, detail, raw }.
        When no verifier spec is registered, returns confirmed=False with
        an explanatory detail (never silently passes).
        """
        kind_name = resolve_receipt_kind(protocol, action)
        if kind_name is None:
            return {
                "confirmed": False,
                "detail": (
                    f"No receipt verifier spec for ({protocol}, {action}). "
                    "Tx may have succeeded — RPC verification skipped."
                ),
                "raw": {},
            }
        # Import lazily so the watcher stays importable without pulling
        # the full reader chain when no verification is needed.
        from src.defi.verification.receipt_reader import verify_receipt
        from src.defi.verification.receipt_table import ReceiptKind

        try:
            kind = ReceiptKind(kind_name)
        except ValueError:
            return {
                "confirmed": False,
                "detail": f"Unknown ReceiptKind value: {kind_name}",
                "raw": {},
            }
        result = await verify_receipt(
            kind=kind, chain=chain, owner=owner, expected=expected or {}
        )
        return {
            "confirmed": bool(getattr(result, "confirmed", False)),
            "detail": str(getattr(result, "detail", "")),
            "kind": str(getattr(getattr(result, "kind", kind), "value", kind.value)),
            "raw": dict(getattr(result, "raw", {}) or {}),
        }

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
