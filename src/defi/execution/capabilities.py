"""Capability registry: maps (chain, protocol, action) → adapter."""
from __future__ import annotations

from dataclasses import dataclass

from src.defi.execution.adapters.base import CapabilityResult, YieldAdapter


@dataclass
class AdapterRegistry:
    adapters: list[YieldAdapter]

    def find(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        chain_norm = chain.lower()
        protocol_norm = protocol.lower()
        action_norm = action.lower()
        for adapter in self.adapters:
            if chain_norm not in {c.lower() for c in adapter.chains}:
                continue
            if protocol_norm not in {p.lower() for p in adapter.protocols}:
                continue
            if action_norm not in {a.lower() for a in adapter.actions}:
                continue
            verdict = adapter.supports(chain=chain_norm, protocol=protocol_norm, action=action_norm)
            if verdict.supported:
                return verdict
        return CapabilityResult(
            supported=False,
            reason=f"No verified adapter supports {action} on {protocol} ({chain}).",
        )

    def adapter_for(self, *, chain: str, protocol: str, action: str) -> YieldAdapter | None:
        chain_norm = chain.lower()
        protocol_norm = protocol.lower()
        action_norm = action.lower()
        for adapter in self.adapters:
            if chain_norm not in {c.lower() for c in adapter.chains}:
                continue
            if protocol_norm not in {p.lower() for p in adapter.protocols}:
                continue
            if action_norm not in {a.lower() for a in adapter.actions}:
                continue
            verdict = adapter.supports(chain=chain_norm, protocol=protocol_norm, action=action_norm)
            if verdict.supported:
                return adapter
        return None


def build_default_registry() -> AdapterRegistry:
    """Wire the adapter set used by Sentinel runtime (Solana-only).

    The Solana yield builder handles Raydium / Orca / Meteora / Kamino /
    Marinade / Jito / Sanctum / JLP; the wallet-assistant adapter handles
    Solana swap / bridge / stake. All EVM adapters (Enso, Aave V3, Compound V3,
    Curve, Balancer, Uniswap V2/V3/V4, Pendle, ERC-4626, EVM LSTs) were removed
    in the Solana-only cut.
    """
    from src.defi.execution.adapters.solana_yield_builder import SolanaYieldBuilderAdapter
    from src.defi.execution.adapters.wallet_assistant import WalletAssistantAdapter

    return AdapterRegistry(
        adapters=[
            SolanaYieldBuilderAdapter(),
            WalletAssistantAdapter(),
        ]
    )
