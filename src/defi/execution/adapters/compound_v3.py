"""Compound v3 (Comet) supply adapter — emits real ERC20 approve + Comet.supply calldata.

Comet markets are per-base-asset, e.g. USDC market on Ethereum is `cUSDCv3`.
Selector for supply(asset, amount) is 0xf2b9fdb8.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.defi.execution.adapters.aave_v3 import _encode_address, _encode_uint256, _to_unit
from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step

# Verified Comet (cToken v3) addresses, base-asset → comet contract per chain.
_COMET_BY_CHAIN_ASSET: dict[tuple[str, str], str] = {
    # Ethereum
    ("ethereum", "USDC"): "0xc3d688b66703497daa19211eedff47f25384cdc3",
    ("ethereum", "USDT"): "0x3afdc9bca9213a35503b077a6072f3d0d5ab0840",
    ("ethereum", "WETH"): "0xa17581a9e3356d9a858b789d68b4d866e593ae94",
    # Polygon
    ("polygon", "USDC"): "0xf25212e676d1f7f89cd72ffee66158f541246445",
    # Arbitrum
    ("arbitrum", "USDC"): "0x9c4ec768c28520b50860ea7a15bd7213a9ff58bf",
    ("arbitrum", "USDC.e"): "0xa5edbdd9646f8dff606d7448e414884c7d905dca",
    # Base
    ("base", "USDC"): "0xb125e6687d4313864e53df431d5425969c15eb2f",
    ("base", "USDBC"): "0x9c4ec768c28520b50860ea7a15bd7213a9ff58bf",
    # Optimism
    ("optimism", "USDC"): "0x2e44e174f7d53f0212823acc11c01a11d58c5bcb",
}

_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
}

# Reuse asset addresses from aave_v3 plus a few comet-specific extras.
from src.defi.execution.adapters.aave_v3 import _ASSETS as _BASE_ASSETS  # noqa: E402

_ASSETS: dict[tuple[str, str], tuple[str, int]] = dict(_BASE_ASSETS)
_ASSETS.setdefault(("base", "USDBC"), ("0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca", 6))
_ASSETS.setdefault(("arbitrum", "USDC.e"), ("0xff970a61a04b1ca14834a43f5de4533ebddb5cc8", 6))


@dataclass
class CompoundV3SupplyAdapter:
    adapter_id: str = "compound-v3-supply"
    chains: frozenset[str] = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base"})
    protocols: frozenset[str] = frozenset({"compound-v3", "compound", "compound v3", "compoundv3", "comet"})
    actions: frozenset[str] = frozenset({"supply", "deposit", "lend"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        chain_norm = chain.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"Compound v3 adapter does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Adapter is for Compound v3, not {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"Compound v3 adapter does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=str(request.amount_in),
            fees={"protocol": "0", "router": "0"},
            metadata={"protocol": "compound-v3", "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        comet_address = _COMET_BY_CHAIN_ASSET.get((chain_norm, request.asset_in.upper()))
        if chain_id is None or comet_address is None:
            raise ValueError(f"Compound v3 adapter has no Comet for {request.asset_in} on {request.chain}.")
        asset_meta = _ASSETS.get((chain_norm, request.asset_in.upper()))
        if asset_meta is None:
            raise ValueError(f"Compound v3 adapter has no token metadata for {request.asset_in} on {request.chain}.")
        token_address, decimals = asset_meta
        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        approve_calldata = "0x095ea7b3" + _encode_address(comet_address) + _encode_uint256(amount_units)
        # Comet.supply(address asset, uint256 amount) -> 0xf2b9fdb8
        supply_calldata = "0xf2b9fdb8" + _encode_address(token_address) + _encode_uint256(amount_units)

        approve_step = make_step(
            index=1,
            action="approve",
            title=f"Approve {request.asset_in} for Compound v3 Comet",
            description=f"Approve {request.amount_in} {request.asset_in} so Comet can pull funds.",
            chain=request.chain,
            wallet="MetaMask",
            protocol="compound-v3",
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            slippage_bps=0,
            gas_estimate_usd=1.4,
            duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=token_address,
                data=approve_calldata,
                value="0x0",
                spender=comet_address,
            ),
            risk_warnings=["Approval allows the Comet contract to pull the exact amount you authorize."],
        )
        supply_step = make_step(
            index=2,
            action="supply",
            title=f"Supply {request.asset_in} to Compound v3",
            description=f"Deposit {request.amount_in} {request.asset_in} into the {request.asset_in} Comet market.",
            chain=request.chain,
            wallet="MetaMask",
            protocol="compound-v3",
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"c{request.asset_in}v3",
            slippage_bps=0,
            gas_estimate_usd=2.5,
            duration_estimate_s=15,
            depends_on=[approve_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=comet_address,
                data=supply_calldata,
                value="0x0",
                spender=comet_address,
            ),
            risk_warnings=["Compound supply APY varies with utilization; treat headline APY as an estimate."],
        )
        return [approve_step, supply_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(confirmed=False, detail="Compound v3 verification deferred to V2 (post-deposit balance read).")
