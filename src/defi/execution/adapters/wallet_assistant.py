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
        return VerifyResult(confirmed=False, detail="Wallet assistant verification handled by SimulationPreview receipt flow.")
