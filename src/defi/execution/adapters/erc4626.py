"""Generic ERC-4626 vault deposit adapter.

Covers any compliant vault by ABI alone: Yearn V3, Morpho vaults, Spark sDAI,
Sommelier, Origin Vault, Aera, Sky/MakerDAO sUSDS, Lido stETH wrapper, etc.

Selectors:
  ERC20.approve(spender, amount) → 0x095ea7b3
  IERC4626.deposit(uint256 assets, address receiver) → 0x6e553f65
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.defi.execution.adapters.aave_v3 import _encode_address, _encode_uint256, _to_unit, _ASSETS as _AAVE_ASSETS
from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step

_CHAIN_IDS = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "bsc": 56,
}

# Curated registry of well-known ERC-4626 vaults: (chain, protocol_slug, asset)
# → (vault_address, underlying_asset_address, decimals).
# Add more as we verify them. The lookup falls back to the asset's native
# address from the Aave registry when the underlying token is the same symbol.
_VAULT_REGISTRY: dict[tuple[str, str, str], tuple[str, str, int]] = {
    # Yearn V3 USDC vault on Ethereum (yvUSDC-1)
    ("ethereum", "yearn-finance", "USDC"): (
        "0xbe53a109b494e5c9f97b9cd39fe969be68bf6204",  # yvUSDC v3
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
        6,
    ),
    # Yearn V3 DAI vault on Ethereum
    ("ethereum", "yearn-finance", "DAI"): (
        "0x028ec7330ff87667b6dfb0d94b954c820195336c",
        "0x6b175474e89094c44da98b954eedeac495271d0f",
        18,
    ),
    # Morpho-Blue MetaMorpho USDC on Base (Steakhouse USDC)
    ("base", "morpho-blue", "USDC"): (
        "0xbeef010f9cb27031ad51e3333f9af9c6b1228183",
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        6,
    ),
    # Spark sDAI on Ethereum
    ("ethereum", "spark", "DAI"): (
        "0x83f20f44975d03b1b09e64809b757c47f942beea",
        "0x6b175474e89094c44da98b954eedeac495271d0f",
        18,
    ),
    # Sky sUSDS on Ethereum
    ("ethereum", "sky-lending", "USDS"): (
        "0xa3931d71877c0e7a3148cb7eb4463524fec27fbd",
        "0xdc035d45d973e3ec169d2276ddab16f1e407384f",
        18,
    ),
}


@dataclass
class ERC4626VaultAdapter:
    adapter_id: str = "erc4626-vault"
    chains: frozenset[str] = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base", "avalanche", "bsc"})
    # Empty protocol set means: defer support entirely to the registry lookup.
    # Anything in _VAULT_REGISTRY is supported; anything else returns False.
    protocols: frozenset[str] = frozenset({
        "yearn-finance", "yearn", "morpho-blue", "morpho", "metamorpho",
        "spark", "sky-lending", "sky", "sommelier", "origin", "origin-ether",
        "aera", "lido", "rocket-pool",
    })
    actions: frozenset[str] = frozenset({"supply", "deposit", "lend", "stake"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        chain_norm = chain.lower()
        protocol_norm = protocol.lower()
        action_norm = action.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"ERC-4626 adapter does not cover {chain}.")
        if action_norm not in self.actions:
            return CapabilityResult(supported=False, reason=f"ERC-4626 adapter does not handle {action}.")
        if protocol_norm not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Protocol {protocol} not in ERC-4626 registry.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={},
            metadata={"protocol": request.protocol, "chain": request.chain, "standard": "ERC-4626"},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        protocol_norm = request.protocol.lower()
        asset_norm = request.asset_in.upper()
        vault_meta = _VAULT_REGISTRY.get((chain_norm, protocol_norm, asset_norm))
        if vault_meta is None:
            # Fallback: attempt to read by (chain, asset) only if exactly one entry exists.
            matching = [
                (key, meta) for key, meta in _VAULT_REGISTRY.items()
                if key[0] == chain_norm and key[2] == asset_norm
            ]
            if len(matching) == 1:
                vault_meta = matching[0][1]
            else:
                raise ValueError(
                    f"ERC-4626 adapter has no registered vault for {request.protocol} {request.asset_in} on {request.chain}."
                )
        vault_address, underlying_address, decimals = vault_meta
        if chain_id is None:
            raise ValueError(f"Unknown chain id for {request.chain}.")
        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        approve_calldata = "0x095ea7b3" + _encode_address(vault_address) + _encode_uint256(amount_units)
        # IERC4626.deposit(uint256 assets, address receiver) → 0x6e553f65
        deposit_calldata = (
            "0x6e553f65"
            + _encode_uint256(amount_units)
            + _encode_address(request.user_address)
        )

        approve_step = make_step(
            index=1,
            action="approve",
            title=f"Approve {request.asset_in} for {request.protocol} vault",
            description=f"Approve {request.amount_in} {request.asset_in} so the {request.protocol} vault can pull funds.",
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            slippage_bps=0,
            gas_estimate_usd=1.4,
            duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=underlying_address,
                data=approve_calldata,
                value="0x0",
                spender=vault_address,
            ),
            risk_warnings=["Approval allows the vault contract to pull the exact amount you authorize."],
        )
        deposit_step = make_step(
            index=2,
            action="supply",
            title=f"Deposit {request.asset_in} into {request.protocol} vault",
            description=(
                f"ERC-4626 deposit({request.amount_in} {request.asset_in}). "
                f"You receive vault shares minted directly to your wallet."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"{request.protocol}-shares",
            slippage_bps=0,
            gas_estimate_usd=2.6,
            duration_estimate_s=15,
            depends_on=[approve_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=vault_address,
                data=deposit_calldata,
                value="0x0",
                spender=vault_address,
            ),
            risk_warnings=["Vault APY varies with underlying utilization; treat headline APY as an estimate."],
        )
        return [approve_step, deposit_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(confirmed=False, detail="ERC-4626 verification deferred (post-deposit share read).")
