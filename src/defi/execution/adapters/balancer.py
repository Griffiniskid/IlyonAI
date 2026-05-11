"""Balancer V2 single-asset join adapter (Phase 6 follow-up).

Balancer V2 lets you join a weighted / stable pool with a single token by
encoding userData = (kind=EXACT_TOKENS_IN_FOR_BPT_OUT(1), amountsIn[], minBPT).
The Vault contract is the same on every EVM chain we cover.

Vault.joinPool ABI:
  joinPool(bytes32 poolId, address sender, address recipient, JoinPoolRequest request)
  JoinPoolRequest = (address[] assets, uint256[] maxAmountsIn, bytes userData, bool fromInternalBalance)
  selector: 0xb95cac28
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from eth_abi import encode as abi_encode  # type: ignore

from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step


_VAULT_ADDRESS = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"  # all EVM chains
_JOINPOOL_SELECTOR = "0xb95cac28"
_APPROVE_SELECTOR = "0x095ea7b3"

_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "gnosis": 100,
}

# (chain, pool_key) -> {poolId, assets[(addr, decimals, symbol)]}
# poolId is the 32-byte ID Balancer uses internally; it embeds the pool
# contract address in its high bytes. These IDs are stable and verified
# from the Balancer subgraph as of 2026-05.
_BALANCER_POOLS: dict[tuple[str, str], dict] = {
    # Ethereum — Stable Pool: bb-aUSD V3 (USDC / DAI / USDT)
    ("ethereum", "bbausd"): {
        "poolId": "0xfebb0bbf162e64fb9d0dfe186e517d84c395f016000000000000000000000502",
        "assets": [
            ("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
            ("DAI", "0x6b175474e89094c44da98b954eedeac495271d0f", 18),
            ("USDT", "0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
        ],
    },
    # Ethereum — wstETH/WETH 50/50
    ("ethereum", "wsteth-weth"): {
        "poolId": "0x32296969ef14eb0c6d29669c550d4a0449130230000200000000000000000080",
        "assets": [
            ("wstETH", "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0", 18),
            ("WETH", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
        ],
    },
    # Polygon — wstETH/WETH 50/50
    ("polygon", "wsteth-weth"): {
        "poolId": "0x9791d590788598535278552eecd4b211bfc790cb000200000000000000000bd5",
        "assets": [
            ("wstETH", "0x03b54a6e9a984069379fae1a4fc4dbae93b3bccd", 18),
            ("WETH", "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619", 18),
        ],
    },
    # Arbitrum — wstETH/WETH 50/50
    ("arbitrum", "wsteth-weth"): {
        "poolId": "0x9791d590788598535278552eecd4b211bfc790cb000200000000000000000498",
        "assets": [
            ("wstETH", "0x5979d7b546e38e414f7e9822514be443a4800529", 18),
            ("WETH", "0x82af49447d8a07e3bd95bd0d56f35241523fbab1", 18),
        ],
    },
    # Optimism — rETH/WETH
    ("optimism", "reth-weth"): {
        "poolId": "0x4fd63966879300cafafbb35d157dc5229278ed230000000000000000000000d4",
        "assets": [
            ("WETH", "0x4200000000000000000000000000000000000006", 18),
            ("rETH", "0x9bcef72be871e61ed4fbbc7630889bee758eb81d", 18),
        ],
    },
}


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


def _resolve_pool(chain: str, pool_hint: str | None, asset_in: str) -> tuple[str, dict] | None:
    chain_l = chain.lower()
    if pool_hint:
        ph = pool_hint.lower()
        for (c, k), meta in _BALANCER_POOLS.items():
            if c != chain_l:
                continue
            if k == ph or meta["poolId"].lower() == ph:
                return k, meta
    asset_u = asset_in.upper()
    for (c, k), meta in _BALANCER_POOLS.items():
        if c != chain_l:
            continue
        if any(sym.upper() == asset_u for sym, _, _ in meta["assets"]):
            return k, meta
    return None


def _encode_join_user_data(amounts_in: list[int], min_bpt: int) -> bytes:
    """userData for EXACT_TOKENS_IN_FOR_BPT_OUT (kind=1)."""
    return abi_encode(["uint256", "uint256[]", "uint256"], [1, amounts_in, min_bpt])


def _encode_join_pool_calldata(
    pool_id: str,
    sender: str,
    recipient: str,
    assets: list[str],
    max_amounts_in: list[int],
    user_data: bytes,
) -> str:
    """Hand-encode joinPool(bytes32, address, address, (address[], uint256[], bytes, bool))."""
    pool_id_bytes = bytes.fromhex(pool_id[2:] if pool_id.startswith("0x") else pool_id)
    if len(pool_id_bytes) != 32:
        raise ValueError(f"poolId must be 32 bytes, got {len(pool_id_bytes)}")
    data = abi_encode(
        [
            "bytes32",
            "address",
            "address",
            "(address[],uint256[],bytes,bool)",
        ],
        [
            pool_id_bytes,
            sender,
            recipient,
            (assets, max_amounts_in, user_data, False),
        ],
    )
    return _JOINPOOL_SELECTOR + data.hex()


@dataclass
class BalancerSingleAssetAdapter:
    adapter_id: str = "balancer-single-asset-join"
    chains: frozenset[str] = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base"})
    protocols: frozenset[str] = frozenset({"balancer", "balancer-v2", "balancer-v3"})
    actions: frozenset[str] = frozenset({"deposit_lp", "add_liquidity", "provide_liquidity"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain.lower() not in self.chains:
            return CapabilityResult(supported=False, reason=f"Balancer adapter does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Adapter is for Balancer, not {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"Balancer adapter does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=str(request.amount_in),
            fees={"protocol": "0.05%", "router": "0"},
            metadata={"protocol": "balancer", "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"Balancer adapter cannot build on chain {request.chain}.")

        extra = request.extra or {}
        pool_hint = extra.get("pool_key") or extra.get("pool_address") or extra.get("poolAddress")
        resolved = _resolve_pool(chain_norm, pool_hint, request.asset_in)
        if resolved is None:
            raise ValueError(
                f"No Balancer pool registered on {chain_norm} containing {request.asset_in}; "
                "pass extra.pool_key or extra.pool_address for non-canonical pools."
            )
        pool_key, pool_meta = resolved
        pool_id = pool_meta["poolId"]
        assets = pool_meta["assets"]

        asset_u = request.asset_in.upper()
        coin_index = None
        token_address = None
        decimals = None
        asset_addresses: list[str] = []
        for idx, (sym, addr, dec) in enumerate(assets):
            asset_addresses.append(addr)
            if sym.upper() == asset_u and coin_index is None:
                coin_index = idx
                token_address = addr
                decimals = dec
        if coin_index is None:
            raise ValueError(
                f"Balancer pool {pool_key} on {chain_norm} does not contain {asset_u}; "
                f"assets = {[s for s, _, _ in assets]}."
            )

        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        max_amounts_in = [0] * len(assets)
        max_amounts_in[coin_index] = amount_units

        slippage_bps = max(int(request.slippage_bps or 50), 10)
        # Conservative minBPT: scale single-asset value to 18-decimal BPT, then apply slippage.
        scale_to_18 = 10 ** (18 - decimals) if decimals is not None and decimals < 18 else 1
        scale_down_18 = 10 ** (decimals - 18) if decimals is not None and decimals > 18 else 1
        bpt_target = amount_units * scale_to_18 // scale_down_18
        min_bpt = (bpt_target * (10_000 - slippage_bps)) // 10_000

        user_data = _encode_join_user_data(max_amounts_in, min_bpt)
        join_calldata = _encode_join_pool_calldata(
            pool_id=pool_id,
            sender=request.user_address,
            recipient=request.user_address,
            assets=asset_addresses,
            max_amounts_in=max_amounts_in,
            user_data=user_data,
        )

        approve_calldata = (
            _APPROVE_SELECTOR + _encode_address(_VAULT_ADDRESS) + _encode_uint256(amount_units)
        )

        approve_step = make_step(
            index=1,
            action="approve",
            title=f"Approve {request.asset_in} for Balancer Vault",
            description=(
                f"Approve {request.amount_in} {request.asset_in} so the Balancer Vault "
                f"can pull funds for the joinPool call."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol="balancer",
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
                spender=_VAULT_ADDRESS,
            ),
            risk_warnings=[
                "Approval grants Balancer Vault the exact amount you authorize.",
            ],
        )
        join_step = make_step(
            index=2,
            action="join_pool",
            title=f"Join Balancer {pool_key} pool",
            description=(
                f"Single-asset join of {request.amount_in} {request.asset_in} into "
                f"Balancer {pool_key} ({len(assets)}-asset pool). "
                f"Slippage cap {slippage_bps / 100:.2f}% on minimum BPT received."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol="balancer",
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"bal-{pool_key.upper()}-BPT",
            slippage_bps=slippage_bps,
            gas_estimate_usd=4.5,
            duration_estimate_s=20,
            depends_on=[approve_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=_VAULT_ADDRESS,
                data=join_calldata,
                value="0x0",
                spender=_VAULT_ADDRESS,
            ),
            risk_warnings=[
                "Single-asset joins incur Balancer's price-impact fee.",
                "BPT represents pooled balance — redeem to base assets later.",
            ],
        )
        return [approve_step, join_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(
            confirmed=False,
            detail="Balancer verification requires on-chain BPT balance read.",
        )
