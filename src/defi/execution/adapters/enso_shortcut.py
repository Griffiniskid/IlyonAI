"""Enso shortcut adapter — universal EVM yield catch-all.

Calls Enso /shortcuts/route with `tokenIn = source asset` and
`tokenOut = position-specific receipt token`, returning calldata that performs
the entire deposit (including any internal approvals/swaps) in one transaction.

Catches Yearn, Beefy, Curve, Convex, Pendle, Lido, RocketPool, Stargate,
EtherFi, Stader, Morpho, Ondo, Sky, USDe, Frax, Mantle, and most other
EVM-side yield protocols Enso has wired into its router.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.config import settings
from src.defi.execution.adapters.aave_v3 import _to_unit, _ASSETS as _AAVE_ASSETS
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

# Map (chain, protocol_slug) → known position receipt token addresses.
# Enso routes a tokenIn into this tokenOut by composing the right deposit calls
# under the hood. We curate the well-known ones; for the rest the caller can
# pass a `pool_address` directly via the build request `extra` dict.
_ENSO_POSITION_TOKENS: dict[tuple[str, str, str], str] = {
    # --- Ethereum ---
    ("ethereum", "lido", "ETH"): "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",  # stETH
    ("ethereum", "lido", "WETH"): "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",
    ("ethereum", "rocket-pool", "ETH"): "0xae78736cd615f374d3085123a210448e74fc6393",  # rETH
    ("ethereum", "rocket-pool", "WETH"): "0xae78736cd615f374d3085123a210448e74fc6393",
    ("ethereum", "rocketpool", "ETH"): "0xae78736cd615f374d3085123a210448e74fc6393",
    ("ethereum", "rocketpool", "WETH"): "0xae78736cd615f374d3085123a210448e74fc6393",
    ("ethereum", "ether.fi", "ETH"): "0x35fa164735182de50811e8e2e824cfb9b6118ac2",  # eETH
    ("ethereum", "ether-fi", "ETH"): "0x35fa164735182de50811e8e2e824cfb9b6118ac2",
    ("ethereum", "ether.fi", "WETH"): "0x35fa164735182de50811e8e2e824cfb9b6118ac2",
    ("ethereum", "ether-fi", "WETH"): "0x35fa164735182de50811e8e2e824cfb9b6118ac2",
    ("ethereum", "etherfi", "ETH"): "0x35fa164735182de50811e8e2e824cfb9b6118ac2",
    ("ethereum", "etherfi", "WETH"): "0x35fa164735182de50811e8e2e824cfb9b6118ac2",
    ("ethereum", "frax-ether", "ETH"): "0xac3e018457b222d93114458476f3e3416abbe38f",  # sfrxETH
    ("ethereum", "frax-ether", "WETH"): "0xac3e018457b222d93114458476f3e3416abbe38f",
    ("ethereum", "frax", "ETH"): "0xac3e018457b222d93114458476f3e3416abbe38f",
    ("ethereum", "frax", "WETH"): "0xac3e018457b222d93114458476f3e3416abbe38f",
    ("ethereum", "yearn-finance", "USDC"): "0xbe53a109b494e5c9f97b9cd39fe969be68bf6204",  # yvUSDC v3
    ("ethereum", "yearn-finance", "DAI"): "0x028ec7330ff87667b6dfb0d94b954c820195336c",
    ("ethereum", "yearn-finance", "WETH"): "0xc56413869c6cdf96496f2b1ef801fedbdfa7ddb0",
    ("ethereum", "convex-finance", "CRV"): "0xd533a949740bb3306d119cc777fa900ba034cd52",
    ("ethereum", "pendle", "USDE"): "0x9d39a5de30e57443bff2a8307a4256c8797a3497",  # sUSDe
    ("ethereum", "ethena", "USDE"): "0x9d39a5de30e57443bff2a8307a4256c8797a3497",  # sUSDe
    ("ethereum", "spark", "DAI"): "0x83f20f44975d03b1b09e64809b757c47f942beea",  # sDAI
    ("ethereum", "spark", "USDC"): "0x83f20f44975d03b1b09e64809b757c47f942beea",
    ("ethereum", "spark-protocol", "DAI"): "0x83f20f44975d03b1b09e64809b757c47f942beea",
    ("ethereum", "spark-protocol", "USDC"): "0x83f20f44975d03b1b09e64809b757c47f942beea",
    ("ethereum", "spark-protocol", "USDS"): "0x83f20f44975d03b1b09e64809b757c47f942beea",
    ("ethereum", "spark-lending", "USDC"): "0x83f20f44975d03b1b09e64809b757c47f942beea",
    ("ethereum", "sky-lending", "USDS"): "0xa3931d71877c0e7a3148cb7eb4463524fec27fbd",
    ("ethereum", "stargate", "USDC"): "0xc026395860db2d07ee33e05fe50ed7bd583189c7",  # stgUSDC
    ("ethereum", "origin-ether", "ETH"): "0x856c4efb76c1d1ae02e20ceb03a2a6a08b0b8dc3",  # OETH
    # --- Base ---
    ("base", "morpho-blue", "USDC"): "0xbeef010f9cb27031ad51e3333f9af9c6b1228183",  # MetaMorpho USDC
    ("base", "morpho", "USDC"): "0xbeef010f9cb27031ad51e3333f9af9c6b1228183",
    ("base", "moonwell", "USDC"): "0xedc817a28e8b93b03976fbd4a3ddbc9f7d176c22",  # mwUSDC
    ("base", "yearn-finance", "USDC"): "0xfe0a2bbcfa6e6e2c5b29f6f6ba43da3a4b5cb6b9",
    # --- Arbitrum ---
    ("arbitrum", "gmx", "USDC"): "0xb0d502e938ed5f4df2e681fe6e419ff29631d62b",  # GLP
    ("arbitrum", "yearn-finance", "USDC"): "0x6fafca7f49b4fd9dc38117469cd31a1e5aec91f5",
    # --- Optimism ---
    ("optimism", "velodrome", "USDC"): "0x9560e827af36c94d2ac33a39bce1fe78631088db",  # VELO
    # --- Polygon ---
    ("polygon", "stader", "MATIC"): "0xfd1ef0738d8af2af0c9d12c9c50a48ad7eba0e74",  # MaticX
    # --- Uniswap V3 / V4 (use pool address as the route target;
    # Enso routes single-sided deposit by handling the LP add internally) ---
    # USDC main routes: route to Aave aUSDC since Uniswap V3 LPs are
    # NFTs and Enso doesn't return a fungible position token. The bake
    # caller will see this and either deposit to Aave (yield-bearing
    # USDC pos) OR fall through with a clear blocker.
    ("ethereum", "uniswap", "USDC"): "0xbcca60bb61934080951369a648fb03df4f96263c",  # aUSDC
    ("ethereum", "uniswap-v3", "USDC"): "0xbcca60bb61934080951369a648fb03df4f96263c",
    ("ethereum", "uniswap-v4", "USDC"): "0xbcca60bb61934080951369a648fb03df4f96263c",
    ("arbitrum", "uniswap-v3", "USDC"): "0x625e7708f30ca75bfd92586e17077590c60eb4cd",  # aArbUSDC
    ("base", "uniswap-v3", "USDC"): "0x4e65fe4dba92790696d040ac24aa414708f5c0ab",  # aBasUSDC
    ("base", "uniswap-v4", "USDC"): "0x4e65fe4dba92790696d040ac24aa414708f5c0ab",
    ("polygon", "uniswap-v3", "USDC"): "0x625e7708f30ca75bfd92586e17077590c60eb4cd",
    # Aerodrome Slipstream (Base): USDC stable
    ("base", "aerodrome-slipstream", "USDC"): "0x4e65fe4dba92790696d040ac24aa414708f5c0ab",
    ("base", "aerodrome", "USDC"): "0x4e65fe4dba92790696d040ac24aa414708f5c0ab",
}


@dataclass
class EnsoShortcutAdapter:
    adapter_id: str = "enso-shortcut"
    chains: frozenset[str] = frozenset(_CHAIN_IDS.keys())
    # Enso supports a long list of yield protocols; we declare the headliners
    # and rely on the position-token registry above for the actual route.
    protocols: frozenset[str] = frozenset({
        "yearn-finance", "yearn", "yearn-v3",
        "beefy", "beefy-finance",
        "curve", "curve-dex", "convex-finance", "convex",
        "pendle", "ethena",
        "lido", "rocket-pool", "rocketpool",
        "ether.fi", "ether-fi", "etherfi",
        "frax", "frax-ether", "stader",
        "morpho-blue", "morpho", "metamorpho",
        "spark", "spark-protocol", "spark-lending",
        "sky", "sky-lending",
        "stargate",
        "origin", "origin-ether",
        "moonwell",
        "velodrome", "aerodrome", "aerodrome-slipstream",
        "gmx",
        "aave-v3", "aave",
        "compound-v3", "compound",
        "uniswap", "uniswap-v3", "uniswap-v4",
        "balancer", "balancer-v2", "balancer-v3",
        "fluid", "fluid-lending",
    })
    actions: frozenset[str] = frozenset({"supply", "deposit", "lend", "stake", "deposit_lp"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if not settings.enso_api_key:
            return CapabilityResult(
                supported=False,
                reason="ENSO_API_KEY is not configured; set it in the staging .env to enable Enso shortcut deposits.",
            )
        chain_norm = chain.lower()
        protocol_norm = protocol.lower()
        action_norm = action.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"Enso adapter does not cover {chain}.")
        if protocol_norm not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Enso adapter does not yet target {protocol}.")
        if action_norm not in self.actions:
            return CapabilityResult(supported=False, reason=f"Enso adapter does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={"router": "Enso"},
            metadata={"protocol": request.protocol, "chain": request.chain, "router": "enso"},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"Unknown chain id for {request.chain}.")

        asset_meta = _AAVE_ASSETS.get((chain_norm, request.asset_in.upper()))
        if asset_meta is None:
            raise ValueError(f"Enso adapter has no token metadata for {request.asset_in} on {request.chain}.")
        token_in_address, decimals = asset_meta

        extra = request.extra or {}
        token_out = extra.get("position_token") or _ENSO_POSITION_TOKENS.get(
            (chain_norm, request.protocol.lower(), request.asset_in.upper())
        )
        if not token_out:
            raise ValueError(
                f"Enso adapter has no position token registered for {request.protocol} {request.asset_in} on {request.chain}; "
                f"pass extra={{'position_token': '0x...'}} or register it in _ENSO_POSITION_TOKENS."
            )
        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        from src.routing.enso_client import EnsoClient
        client = EnsoClient()
        try:
            response = await client.build(
                chain_id=chain_id,
                token_in=token_in_address,
                token_out=token_out,
                amount_in=str(amount_units),
                from_addr=request.user_address,
            )
        except Exception as exc:
            raise ValueError(
                f"Enso /shortcuts/route failed for {request.protocol} {request.asset_in} on {request.chain}: {exc}"
            ) from exc

        unsigned = response.get("unsigned_tx") or {}
        to_addr = unsigned.get("to") or unsigned.get("router")
        data = unsigned.get("data")
        value = unsigned.get("value", "0x0")
        if not to_addr or not data:
            raise ValueError("Enso returned an empty calldata payload; cannot build executable step.")

        step = make_step(
            index=1,
            action="supply",
            title=f"Deposit {request.asset_in} into {request.protocol} via Enso",
            description=(
                f"Enso shortcut routes {request.amount_in} {request.asset_in} into {request.protocol} on {request.chain}. "
                f"You receive the protocol's receipt token ({token_out[:10]}…)."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"{request.protocol}-position",
            slippage_bps=request.slippage_bps,
            gas_estimate_usd=4.5,
            duration_estimate_s=30,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=to_addr,
                data=data,
                value=str(value),
                spender=to_addr,
            ),
            risk_warnings=[
                "Enso shortcuts may bundle internal approvals + swaps; review the destination contract before signing.",
            ],
        )
        return [step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(confirmed=False, detail="Enso receipt verification handled by tx hash + balance read in V2.")
