"""Enso shortcut adapter — universal EVM yield catch-all.

For every EVM chain Enso supports we:
  1. Resolve `tokenIn` from request.asset_in (symbol or address) via the
     asset registry + on-chain decimals() fallback.
  2. Resolve `tokenOut` (Enso position token) via the dynamic /tokens
     resolver. This auto-discovers Aave V3 static atokens, Compound V3
     Comets, Curve LP tokens, Balancer BPTs, Yearn vaults, Morpho vaults,
     Spark sDAI, Lido stETH, RocketPool rETH, EtherFi eETH, Frax sfrxETH,
     Stargate, Stader, Moonwell, GMX, Velodrome, Aerodrome, etc.
  3. Call /shortcuts/route which returns bundled calldata performing the
     full deposit (including internal approvals + swaps) in one tx.

V3 (uniswap-v3, pancake-v3, aerodrome-slipstream) NFT positions are
handled separately by the V3 router adapter — not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.config import settings
from src.data.asset_registry import resolve_any_evm_token, NATIVE_PLACEHOLDER
from src.data.enso_token_resolver import (
    ENSO_CHAIN_IDS,
    normalize_protocol,
    resolve_position,
)
from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step


def _to_unit(amount: Decimal, decimals: int) -> int:
    quant = Decimal(10) ** decimals
    return int((amount * quant).to_integral_value())


_SUPPORTED_PROTOCOLS = frozenset({
    "aave-v3", "aave", "aavev3",
    "aave-v2", "aave-v3-prime", "aave-static",
    "compound-v3", "compound", "compoundv3",
    "curve", "curve-dex", "curve-lending",
    "balancer", "balancer-v2", "balancer-v3",
    "yearn-finance", "yearn", "yearn-v3",
    "morpho-blue", "morpho", "metamorpho",
    "spark", "spark-protocol", "spark-lending",
    "sky", "sky-lending", "makerdao",
    "lido", "rocket-pool", "rocketpool",
    "ether.fi", "ether-fi", "etherfi",
    "frax", "frax-ether", "frx-ether",
    "ethena", "pendle",
    "stargate", "moonwell",
    "gmx", "velodrome", "velodrome-v2", "aerodrome", "aerodrome-v1",
    "stader", "origin", "origin-ether",
    "fluid", "fluid-lending",
    "beefy", "beefy-clm", "beefy-finance",
    "ichi", "ichi-vaults", "steer", "steer-protocol", "gamma", "arrakis",
    "tokemak", "tokemak-autoeth",
})

_SUPPORTED_CHAINS = frozenset({
    "ethereum", "polygon", "arbitrum", "optimism", "base",
    "avalanche", "bsc", "binance", "linea", "zksync",
    "scroll", "gnosis", "sonic", "soneium", "plasma", "ink",
})


@dataclass
class EnsoShortcutAdapter:
    adapter_id: str = "enso-shortcut"
    chains: frozenset[str] = _SUPPORTED_CHAINS
    protocols: frozenset[str] = _SUPPORTED_PROTOCOLS
    actions: frozenset[str] = frozenset({"supply", "deposit", "lend", "stake", "deposit_lp"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if not settings.enso_api_key:
            return CapabilityResult(
                supported=False,
                reason="ENSO_API_KEY is not configured; set it in the .env to enable Enso shortcut deposits.",
            )
        chain_norm = chain.lower()
        protocol_norm = protocol.lower()
        action_norm = action.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"Enso adapter does not cover {chain}.")
        if protocol_norm not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Enso adapter does not target {protocol}.")
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
        chain_id = ENSO_CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"Enso: unknown chain id for {request.chain}.")

        token_in_meta = await resolve_any_evm_token(chain_norm, request.asset_in)
        if token_in_meta is None:
            raise ValueError(
                f"Enso: cannot resolve token {request.asset_in} on {request.chain}. "
                f"Pass an ERC20 contract address or a known symbol."
            )
        token_in_addr, decimals = token_in_meta

        extra = request.extra or {}
        protocol_slug = normalize_protocol(request.protocol)

        # Allow callers to override the position token (V3 NFT pool addresses,
        # bespoke vaults not in Enso's index).
        explicit_position = extra.get("position_token")

        if explicit_position:
            token_out_addr = explicit_position
            apy_hint = extra.get("apy")
            tvl_hint = extra.get("tvl")
        else:
            # Aliases here cover protocol-slug variants Enso uses internally
            # — when a hub's main alias misses (e.g. frax → frax-sfrxeth),
            # walk a fallback list before declaring unsupported. Without this
            # Frax/Stader/Kelp/Renzo style LST hubs surface adapter_build_failed
            # even though Enso indexes them under a sibling name.
            _SLUG_FALLBACKS: dict[str, list[str]] = {
                "frax-sfrxeth": ["frax-finance", "frax-ether", "frax", "staked-frax-ether"],
                "stader-ethx": ["stader-labs", "stader", "staked-eth"],
                "kelp-rseth": ["kelp-dao", "kelp"],
                "swell-rsweth": ["swell-network", "swell", "swelleth"],
                "renzo-ezeth": ["renzo-protocol", "renzo"],
                "puffer-pufeth": ["puffer-finance", "puffer"],
                "mantle-staked-eth": ["mantle-lsp", "mantle"],
            }
            tried = [protocol_slug] + _SLUG_FALLBACKS.get(protocol_slug, [])
            position = None
            for try_slug in tried:
                position = await resolve_position(
                    chain_id=chain_id,
                    protocol_slug=try_slug,
                    underlying_addr=token_in_addr,
                )
                if position is not None:
                    break
            # Last-resort hardcoded receipt-token addresses for LST hubs that
            # Enso doesn't index under any slug we know. These are canonical
            # mainnet contracts; the Enso /shortcuts/route still builds the
            # swap path because the receipt tokens are tradable on Curve /
            # Uniswap. Empty per chain when no override.
            override_used = False
            if position is None:
                _RECEIPT_BY_HUB: dict[int, dict[str, str]] = {
                    1: {  # ethereum
                        "frax-sfrxeth": "0xac3e018457b222d93114458476f3e3416abbe38f",
                        "kelp-rseth": "0xa1290d69c65a6fe4df752f95823fae25cb99e5a7",
                        "swell-rsweth": "0xfae103dc9cf190ed75350761e95403b7b8afa6c0",
                        "renzo-ezeth": "0xbf5495efe5db9ce00f80364c8b423567e58d2110",
                        "puffer-pufeth": "0xd9a442856c234a39a81a089c06451ebaa4306a72",
                        "mantle-staked-eth": "0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa",
                    },
                }
                hub_map = _RECEIPT_BY_HUB.get(chain_id, {})
                override = hub_map.get(protocol_slug)
                if override:
                    token_out_addr = override
                    apy_hint = extra.get("apy")
                    tvl_hint = extra.get("tvl")
                    override_used = True
            if position is None and not override_used and token_in_addr == NATIVE_PLACEHOLDER:
                # Native ETH path — protocol may index WETH as underlying.
                wrapped_meta = await resolve_any_evm_token(chain_norm, "WETH")
                if wrapped_meta:
                    for try_slug in tried:
                        position = await resolve_position(
                            chain_id=chain_id,
                            protocol_slug=try_slug,
                            underlying_addr=wrapped_meta[0],
                        )
                        if position is not None:
                            break
            if position is None and not override_used:
                raise ValueError(
                    f"Enso: no position token indexed for {request.protocol} {request.asset_in} on "
                    f"{request.chain}. Try a different asset or pass extra={{'position_token': '0x...'}}."
                )
            if position is not None:
                token_out_addr = position.position_address
                apy_hint = position.apy
                tvl_hint = position.tvl

        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("Enso: amount_in must be > 0")

        from src.routing.enso_client import EnsoClient
        client = EnsoClient()
        try:
            response = await client.build(
                chain_id=chain_id,
                token_in=token_in_addr,
                token_out=token_out_addr,
                amount_in=str(amount_units),
                from_addr=request.user_address,
                slippage_bps=request.slippage_bps,
            )
        except Exception as exc:
            from src.defi.execution.error_decoder import decode_evm_revert
            decoded = decode_evm_revert(str(exc))
            hint = f" Hint: {decoded}" if decoded else ""
            raise ValueError(
                f"Enso /shortcuts/route failed for {request.protocol} {request.asset_in} on {request.chain}: {exc}.{hint}"
            ) from exc

        unsigned = response.get("unsigned_tx") or {}
        to_addr = unsigned.get("to")
        data = unsigned.get("data")
        value = unsigned.get("value", "0x0")
        gas_estimate = unsigned.get("gas")
        sim = response.get("simulation") or {}
        if not to_addr or not data:
            raise ValueError("Enso returned an empty calldata payload; cannot build executable step.")

        risk_lines = [
            "Enso shortcuts bundle approvals + swaps; review the destination contract before signing.",
            f"Position token: {token_out_addr}",
        ]
        if apy_hint is not None:
            risk_lines.append(f"Pool APY (Enso quote): {apy_hint:.2f}%")
        if tvl_hint is not None:
            try:
                risk_lines.append(f"Pool TVL (Enso quote): ${tvl_hint:,.0f}")
            except (TypeError, ValueError):
                pass
        if sim.get("price_impact_bps") is not None:
            risk_lines.append(f"Quoted price impact: {sim['price_impact_bps']} bps")

        gas_value: str | None = None
        if gas_estimate is not None:
            try:
                gas_value = hex(int(gas_estimate))
            except (TypeError, ValueError):
                gas_value = None

        step = make_step(
            index=1,
            action="supply",
            title=f"Deposit {request.asset_in} into {request.protocol} via Enso",
            description=(
                f"Enso shortcut routes {request.amount_in} {request.asset_in} into {request.protocol} on {request.chain}. "
                f"You receive the protocol's position token ({token_out_addr[:10]}…)."
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
                gas=gas_value,
                spender=to_addr,
            ),
            risk_warnings=risk_lines,
        )
        return [step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(confirmed=False, detail="Enso receipt verified by tx hash + balance read in V2.")
