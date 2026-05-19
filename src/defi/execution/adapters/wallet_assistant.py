"""Wallet-assistant adapter — declares supported swap/bridge/stake routes."""
from __future__ import annotations

from dataclasses import dataclass

from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
    parse_receipt_logs,
)
from src.defi.execution.models import ExecutionStepV3


@dataclass
class WalletAssistantAdapter:
    adapter_id: str = "wallet-assistant"
    chains: frozenset[str] = frozenset({
        "ethereum", "polygon", "arbitrum", "optimism", "base", "bsc", "avalanche", "solana"
    })
    protocols: frozenset[str] = frozenset({"jupiter", "enso", "debridge"})
    actions: frozenset[str] = frozenset({"swap", "bridge", "stake"})
    # V7-043 — canonical ERC-20 Transfer(address,address,uint256) topic0.
    # Wallet-assistant brokers generic swap/bridge/stake. Any successful EVM
    # broadcast emits at least one Transfer; SOMETHING moved is the only
    # honest universal signal we can give without knowing the routed
    # protocol. Caller-side reconciliation refines this against expected
    # delta. Solana receipts are confirmed by the sidecar /verify flow.
    EXPECTED_TOPIC0: str = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain.lower() not in self.chains:
            return CapabilityResult(supported=False, reason=f"Wallet assistant does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Wallet assistant routes via Jupiter/Enso/deBridge, not {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"Wallet assistant does not handle {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={},
            metadata={"protocol": request.protocol, "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        # Wallet assistant builders live in IlyonAi-Wallet-assistant. The
        # Sentinel runtime composes wallet-assistant calls separately as
        # SimulationPreview today; this adapter exists so the registry
        # can advertise capability without forcing a duplicate Python build
        # path. Returning an empty step list signals the runtime to fall
        # back to the legacy SimulationPreview flow for swaps/bridges/stake.
        return []

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        """Confirm any ERC-20 Transfer fired by the broadcast tx.

        Wallet-assistant is the generic catch-all; we cannot know which
        protocol-specific Deposit event to look for, so we treat *any*
        ERC-20 Transfer as "something settled on-chain". Native-asset
        (ETH/MATIC/BNB) only broadcasts and Solana receipts have no ERC-20
        Transfer and fall through to confirmed=False — the SimulationPreview
        flow handles those.
        """
        receipt = request.receipt or (request.expected_position or {}).get("receipt")
        return parse_receipt_logs(receipt, self.EXPECTED_TOPIC0)
