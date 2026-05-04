"""Aave V3 supply adapter — emits real ERC20 approve + Pool.supply calldata."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step

# Aave V3 Pool addresses per chain (verified mainnets).
_AAVE_POOL_ADDRESSES: dict[str, str] = {
    "ethereum": "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
    "polygon": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
    "arbitrum": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
    "optimism": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
    "base": "0xa238dd80c259a72e81d7e4664a9801593f98d1c5",
    "avalanche": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
}

_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
}

# Common asset addresses + decimals per chain. Add more incrementally.
_ASSETS: dict[tuple[str, str], tuple[str, int]] = {
    ("ethereum", "USDC"): ("0xa0b86a33e6441e8e421c6f9e8a37e2bd3df0f0fd", 6),  # canonical USDC.e style; replaced below
    ("ethereum", "USDT"): ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    ("ethereum", "DAI"): ("0x6b175474e89094c44da98b954eedeac495271d0f", 18),
    ("ethereum", "WETH"): ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
    ("polygon", "USDC"): ("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", 6),
    ("polygon", "USDT"): ("0xc2132d05d31c914a87c6611c10748aeb04b58e8f", 6),
    ("arbitrum", "USDC"): ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", 6),
    ("arbitrum", "USDT"): ("0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", 6),
    ("optimism", "USDC"): ("0x0b2c639c533813f4aa9d7837caf62653d097ff85", 6),
    ("base", "USDC"): ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
    ("base", "USDBC"): ("0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca", 6),
}

# Override Ethereum USDC with the canonical mainnet address.
_ASSETS[("ethereum", "USDC")] = ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6)


def _encode_uint256(value: int) -> str:
    if value < 0:
        raise ValueError("uint256 cannot be negative")
    return format(value, "064x")


def _encode_address(address: str) -> str:
    addr = address.lower()
    if addr.startswith("0x"):
        addr = addr[2:]
    if len(addr) != 40:
        raise ValueError(f"invalid address: {address}")
    return ("0" * 24) + addr


def _to_unit(amount: Decimal, decimals: int) -> int:
    quant = Decimal(10) ** decimals
    return int((amount * quant).to_integral_value())


@dataclass
class AaveV3SupplyAdapter:
    adapter_id: str = "aave-v3-supply"
    chains: frozenset[str] = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base", "avalanche"})
    protocols: frozenset[str] = frozenset({"aave-v3", "aave", "aave v3", "aavev3"})
    actions: frozenset[str] = frozenset({"supply", "deposit", "lend"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        chain_norm = chain.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"Aave V3 adapter does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Adapter is for Aave V3, not {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"Aave V3 adapter does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=str(request.amount_in),
            fees={"protocol": "0", "router": "0"},
            metadata={"protocol": "aave-v3", "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        pool_address = _AAVE_POOL_ADDRESSES.get(chain_norm)
        if chain_id is None or pool_address is None:
            raise ValueError(f"Aave V3 adapter cannot build on chain {request.chain}.")

        asset_key = (chain_norm, request.asset_in.upper())
        asset_meta = _ASSETS.get(asset_key)
        if asset_meta is None:
            raise ValueError(f"Aave V3 adapter has no token metadata for {request.asset_in} on {request.chain}.")
        token_address, decimals = asset_meta

        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        # ERC20 approve(spender, amount) -> 0x095ea7b3
        approve_calldata = "0x095ea7b3" + _encode_address(pool_address) + _encode_uint256(amount_units)
        # Aave Pool supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) -> 0x617ba037
        supply_calldata = (
            "0x617ba037"
            + _encode_address(token_address)
            + _encode_uint256(amount_units)
            + _encode_address(request.user_address)
            + _encode_uint256(0)
        )

        approve_step = make_step(
            index=1,
            action="approve",
            title=f"Approve {request.asset_in} for Aave V3 Pool",
            description=f"Approve {request.amount_in} {request.asset_in} so Aave V3 Pool can pull funds.",
            chain=request.chain,
            wallet="MetaMask",
            protocol="aave-v3",
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
                spender=pool_address,
            ),
            risk_warnings=[
                "Approval allows Aave V3 Pool to pull the exact amount you authorize.",
            ],
        )
        supply_step = make_step(
            index=2,
            action="supply",
            title=f"Supply {request.asset_in} to Aave V3",
            description=f"Deposit {request.amount_in} {request.asset_in} into Aave V3 Pool. You receive a{request.asset_in} receipt token.",
            chain=request.chain,
            wallet="MetaMask",
            protocol="aave-v3",
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"a{request.asset_in}",
            slippage_bps=0,
            gas_estimate_usd=2.8,
            duration_estimate_s=15,
            depends_on=[approve_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=pool_address,
                data=supply_calldata,
                value="0x0",
                spender=pool_address,
            ),
            risk_warnings=[
                "Aave supply APY varies with utilization; treat headline APY as an estimate.",
            ],
        )
        return [approve_step, supply_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(confirmed=False, detail="Aave V3 verification requires on-chain balance read; wired in V2.")
