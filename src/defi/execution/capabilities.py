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

    Per plan v3: Enso is the EVM catch-all (Aave V3, Compound V3, Curve,
    Balancer, Yearn, Morpho, Spark, Lido, RocketPool, EtherFi, Frax, Pendle,
    Stargate, Stader, Moonwell, GMX, Velodrome, Aerodrome, Sky, etc.).
    Solana yield builder handles Raydium/Orca/Meteora/Kamino. Wallet-assistant
    handles swap/bridge/stake fallbacks. The V3 NFT-position adapter handles
    Uniswap V3 / PancakeSwap V3 / Aerodrome Slipstream (concentrated liquidity).
    """
    from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter
    from src.defi.execution.adapters.balancer import BalancerSingleAssetAdapter
    from src.defi.execution.adapters.compound_v3 import CompoundV3SupplyAdapter
    from src.defi.execution.adapters.curve import CurveSingleSidedAdapter
    from src.defi.execution.adapters.enso_shortcut import EnsoShortcutAdapter
    from src.defi.execution.adapters.erc4626 import ERC4626VaultAdapter
    from src.defi.execution.adapters.evm_lst import EvmLstDirectMintAdapter
    from src.defi.execution.adapters.pendle_v2 import PendleV2Adapter
    from src.defi.execution.adapters.solana_yield_builder import SolanaYieldBuilderAdapter
    from src.defi.execution.adapters.uniswap_v2 import UniswapV2DualTokenAdapter
    from src.defi.execution.adapters.uniswap_v3_nft import UniswapV3NFTAdapter
    from src.defi.execution.adapters.uniswap_v4 import UniswapV4NativeAdapter
    from src.defi.execution.adapters.wallet_assistant import WalletAssistantAdapter

    return AdapterRegistry(
        adapters=[
            # V4 first so it wins over V3 NFT for uniswap-v4.
            UniswapV4NativeAdapter(),
            UniswapV3NFTAdapter(),
            UniswapV2DualTokenAdapter(),
            # Protocol-native withdraw paths precede Enso so lifecycle actions
            # land on the on-chain encoders instead of a generic Enso route.
            AaveV3SupplyAdapter(),
            CompoundV3SupplyAdapter(),
            CurveSingleSidedAdapter(),
            BalancerSingleAssetAdapter(),
            # LST/LRT direct-mint precedes ERC4626 + Enso so Lido / Rocket Pool /
            # ether.fi / Renzo / Kelp / Swell / Frax / Mantle / Puffer go to
            # the canonical mint contract instead of being intercepted by the
            # generic ERC-4626 share-token path or an Enso route.
            EvmLstDirectMintAdapter(),
            ERC4626VaultAdapter(),
            PendleV2Adapter(),
            EnsoShortcutAdapter(),
            SolanaYieldBuilderAdapter(),
            WalletAssistantAdapter(),
        ]
    )
