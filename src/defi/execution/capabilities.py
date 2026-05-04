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
    """Wire the adapter set used by Sentinel runtime.

    Order matters: more specific adapters first, then generic ERC-4626,
    Enso shortcut as the EVM catch-all, Solana sidecar for Solana,
    wallet-assistant for swaps/bridges/stake.
    """
    from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter
    from src.defi.execution.adapters.compound_v3 import CompoundV3SupplyAdapter
    from src.defi.execution.adapters.erc4626 import ERC4626VaultAdapter
    from src.defi.execution.adapters.enso_shortcut import EnsoShortcutAdapter
    from src.defi.execution.adapters.solana_yield_builder import SolanaYieldBuilderAdapter
    from src.defi.execution.adapters.wallet_assistant import WalletAssistantAdapter

    return AdapterRegistry(
        adapters=[
            AaveV3SupplyAdapter(),
            CompoundV3SupplyAdapter(),
            ERC4626VaultAdapter(),
            EnsoShortcutAdapter(),
            SolanaYieldBuilderAdapter(),
            WalletAssistantAdapter(),
        ]
    )
