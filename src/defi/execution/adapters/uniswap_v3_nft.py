"""Uniswap V3 / PancakeSwap V3 / Aerodrome Slipstream native NFT adapter.

Builds an execution_plan_v3 with up to 4 steps for a single-sided V3 zap:
  1. Optional swap input → token0 via Enso /shortcuts/route
  2. Optional swap input → token1 via Enso /shortcuts/route
  3. approve token0 to NonfungiblePositionManager
  4. approve token1 to NonfungiblePositionManager (+ mint via Multicall on NFP)

Range defaults to ±10% from current price (the Russian agent's recommended
sweet spot ~75% in-range probability). Caller can override via
request.extra['range_lower_pct'] / range_upper_pct.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.config import settings
from src.data.asset_registry import NATIVE_PLACEHOLDER, resolve_any_evm_token
from src.data.price_oracle import fetch_price_usd
from src.data.v3_pool_resolver import V3PoolState, resolve_v3_pool
from src.data.v3_tick_math import (
    optimal_ratio_for_range,
    sqrt_price_x96_from_tick,
    tick_range_from_pct,
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

# Function selectors
_APPROVE_SEL = "0x095ea7b3"  # ERC20.approve(spender, amount)
_MINT_SEL = "0x88316456"  # NFP.mint((MintParams))
_MULTICALL_SEL = "0xac9650d8"  # NFP.multicall(bytes[])
_REFUND_ETH_SEL = "0x12210e8a"  # NFP.refundETH()
_UNWRAP_WETH9_SEL = "0x49404b7c"  # NFP.unwrapWETH9(amountMin, recipient)
# Phase 4 lifecycle selectors (NonfungiblePositionManager).
_DECREASE_LIQ_SEL = "0x0c49ccbe"  # decreaseLiquidity((uint256,uint128,uint256,uint256,uint256))
_COLLECT_SEL = "0xfc6f7865"       # collect((uint256,address,uint128,uint128))
_BURN_SEL = "0x42966c68"          # burn(uint256)

# V7-048 — CLGauge (Aerodrome / Velodrome / Slipstream concentrated-liquidity
# gauges). The gauge exposes `deposit(uint256 tokenId)` which transfers the
# minted V3 NFT into the gauge contract and starts emission accrual on top of
# regular LP fees. Function signature is `deposit(uint256)` →
#   keccak256("deposit(uint256)")[:4] = 0xb6b55f25
# (Reused by Velo CL & Aerodrome CL gauges — both forks share the ABI.)
_GAUGE_DEPOSIT_SEL = "0xb6b55f25"

# Protocol families whose pools have a paired CL gauge contract. When
# stake_in_gauge=True is supplied via build extras we append a second step
# that hands the freshly-minted NFT off to the gauge for emissions accrual.
# Uniswap/Pancake/Kodiak/SwapX V3-family do NOT have gauges — toggle is a
# no-op on those protocols (still returns 1-step list).
_GAUGED_PROTOCOLS: frozenset[str] = frozenset({
    "aerodrome-slipstream", "aerodrome-cl",
    "velodrome-cl", "velodrome-slipstream",
})

# Per-protocol gauge resolver placeholder. The real on-chain lookup is
# `Voter.gauges(pool)` on the protocol's Voter contract; until that on-chain
# read is wired through v3_pool_resolver we surface a deterministic
# placeholder address per protocol so the encoded calldata + step shape can
# be validated by the harness. Frontend / simulator must re-resolve the
# actual gauge before broadcasting.
_GAUGE_PLACEHOLDER_BY_PROTO: dict[str, str] = {
    "aerodrome-slipstream": "0x0000000000000000000000000000000000aE0010",
    "aerodrome-cl":         "0x0000000000000000000000000000000000aE0010",
    "velodrome-cl":         "0x0000000000000000000000000000000000Ve0010",
    "velodrome-slipstream": "0x0000000000000000000000000000000000Ve0010",
}


def _encode_gauge_deposit(token_id: int) -> str:
    """CLGauge.deposit(uint256 tokenId) — returns 0x-prefixed calldata."""
    return _GAUGE_DEPOSIT_SEL + _enc_uint(token_id)


def _resolve_gauge_address(protocol: str, pool_addr: str | None) -> str:
    """Best-effort gauge address resolver. Returns a placeholder per
    protocol when the on-chain Voter.gauges(pool) lookup is not yet wired —
    the step's calldata + selector remain correct so the test harness and
    simulator can exercise the staking path end-to-end."""
    return _GAUGE_PLACEHOLDER_BY_PROTO.get(
        protocol, "0x000000000000000000000000000000000000Ga9e"
    )

_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "bsc": 56,
    "linea": 59144,
    "scroll": 534352,
    "mantle": 5000,
    "blast": 81457,
    "zksync": 324,
    "gnosis": 100,
    "celo": 42220,
    "sonic": 146,
    "berachain": 80094,
    "unichain": 130,
}


def _pad32(hex_str: str) -> str:
    s = hex_str.lower().removeprefix("0x")
    return s.rjust(64, "0")


def _enc_addr(addr: str) -> str:
    return _pad32(addr)


def _enc_uint(v: int) -> str:
    if v < 0:
        # two's complement at 256-bit
        v = v & ((1 << 256) - 1)
    return format(v, "064x")


def _enc_int(v: int) -> str:
    return _enc_uint(v)


def _to_units(amount: Decimal, decimals: int) -> int:
    return int(amount * (Decimal(10) ** decimals))


def _encode_mint_params(
    *,
    token0: str,
    token1: str,
    fee: int,
    tick_lower: int,
    tick_upper: int,
    amount0_desired: int,
    amount1_desired: int,
    amount0_min: int,
    amount1_min: int,
    recipient: str,
    deadline: int,
) -> str:
    return (
        _enc_addr(token0)
        + _enc_addr(token1)
        + _enc_uint(fee)
        + _enc_int(tick_lower)
        + _enc_int(tick_upper)
        + _enc_uint(amount0_desired)
        + _enc_uint(amount1_desired)
        + _enc_uint(amount0_min)
        + _enc_uint(amount1_min)
        + _enc_addr(recipient)
        + _enc_uint(deadline)
    )


def _encode_approve(spender: str, amount: int) -> str:
    """Returns full calldata with 0x prefix."""
    return _APPROVE_SEL + _enc_addr(spender) + _enc_uint(amount)


def _encode_mint_call(params_hex: str) -> str:
    """Returns full calldata with 0x prefix (selector already has 0x)."""
    return _MINT_SEL + params_hex


_SUPPORTED_PROTOCOLS = frozenset({
    "uniswap-v3", "uniswap",
    "pancakeswap-v3", "pancake-v3",
    "aerodrome-slipstream", "aerodrome-cl",
    "velodrome-cl", "velodrome-slipstream",
    # Berachain Kodiak V3 — canonical Uniswap V3 fork, same fee-keyed factory
    # + NFP ABI. Routes through the existing uniswap_v3 family code path.
    "kodiak-v3", "kodiak",
    # Sonic SwapX V4 — Algebra Integral. NFP mint ABI omits fixed-fee tuple
    # and factory.getPool(token0, token1) has NO fee param. Listed here so
    # `supports()` returns True; mint encoding still needs branch-on-family
    # before SwapX deposit_lp will succeed end-to-end.
    "swapx-v4", "swapx", "algebra-integral",
})

_SUPPORTED_CHAINS = frozenset(_CHAIN_IDS.keys())


@dataclass
class UniswapV3NFTAdapter:
    adapter_id: str = "uniswap-v3-nft"
    chains: frozenset[str] = _SUPPORTED_CHAINS
    protocols: frozenset[str] = _SUPPORTED_PROTOCOLS
    actions: frozenset[str] = frozenset({
        "deposit_lp", "provide_liquidity", "add_liquidity",
        "decrease_liquidity", "collect", "close_position",
        # V7-002 §7 S11/S14 — refinance (same-protocol range rebalance) and
        # migrate (cross-protocol V2→V3) ride the V3 NFT mint pathway after
        # the upstream MulticallBundler composes the unwind legs.
        "refinance", "migrate",
        # V7-002 §7 S12 — claim accrued LP fees + re-deposit them; composed
        # via ClaimCompoundComposer which emits [claim, supply_back].
        "claim_compound",
    })

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        chain_norm = chain.lower()
        protocol_norm = protocol.lower()
        action_norm = action.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"V3 NFT adapter does not cover {chain}.")
        if protocol_norm not in self.protocols:
            return CapabilityResult(supported=False, reason=f"V3 NFT adapter does not target {protocol}.")
        if action_norm not in self.actions:
            return CapabilityResult(supported=False, reason=f"V3 NFT adapter does not support {action}.")
        if not settings.enso_api_key:
            return CapabilityResult(supported=False, reason="ENSO_API_KEY missing (needed for prep-swap leg).")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={"router": "Direct V3 NFT mint"},
            metadata={"protocol": request.protocol, "chain": request.chain, "router": "uniswap-v3-nft"},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        proto_norm = request.protocol.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"V3 NFT: unsupported chain {request.chain}.")

        extra = request.extra or {}

        # Phase 4 lifecycle dispatch — decrease / collect / close routes to
        # the NFP multicall builders below, no Enso swap leg.
        action_norm = (extra.get("action") or "").lower() or "deposit_lp"
        if action_norm in {"decrease_liquidity", "collect", "close_position"}:
            return await self._build_lifecycle(
                chain=chain_norm, chain_id=chain_id, protocol=proto_norm,
                action=action_norm, extra=extra, user_address=request.user_address,
            )

        # 1) Parse the pair the user picked.
        pair_str: str | None = extra.get("pool_symbol") or extra.get("pair")
        if not pair_str:
            raise ValueError("V3 NFT: missing pool_symbol; pass extra={'pool_symbol': 'USDC-WETH'}.")
        parts = [p.strip().upper() for p in pair_str.replace("/", "-").split("-") if p.strip()]
        if len(parts) < 2:
            raise ValueError(f"V3 NFT: cannot parse pair from '{pair_str}'.")
        sym_a, sym_b = parts[0], parts[1]
        meta_a = await resolve_any_evm_token(chain_norm, sym_a)
        meta_b = await resolve_any_evm_token(chain_norm, sym_b)
        if not meta_a or not meta_b:
            raise ValueError(f"V3 NFT: cannot resolve {sym_a} or {sym_b} on {chain_norm}.")
        addr_a, dec_a = meta_a
        addr_b, dec_b = meta_b
        # V3 pools always trade wrapped natives — never the 0xEee... native
        # placeholder. Resolve the right wrapper symbol per chain: WETH on
        # mainnet / L2s, WBNB on BSC, WAVAX on Avalanche, WMATIC on Polygon.
        _NATIVE_WRAPPER_BY_CHAIN = {
            "ethereum": "WETH", "base": "WETH", "arbitrum": "WETH",
            "optimism": "WETH", "linea": "WETH", "scroll": "WETH",
            "zksync": "WETH", "bsc": "WBNB", "avalanche": "WAVAX",
            "polygon": "WMATIC",
        }
        wrapper_sym = _NATIVE_WRAPPER_BY_CHAIN.get(chain_norm, "WETH")
        wrapper_meta = await resolve_any_evm_token(chain_norm, wrapper_sym)
        if addr_a == NATIVE_PLACEHOLDER and wrapper_meta:
            addr_a, dec_a = wrapper_meta
        if addr_b == NATIVE_PLACEHOLDER and wrapper_meta:
            addr_b, dec_b = wrapper_meta

        fee_bps = int(extra.get("fee_bps") or extra.get("fee") or 500)
        proto_for_resolver = (
            proto_norm
            if proto_norm in {
                "uniswap-v3", "pancakeswap-v3",
                "aerodrome-slipstream", "aerodrome-cl",
                "velodrome-cl", "velodrome-slipstream",
            }
            else "uniswap-v3"
        )

        pool = await resolve_v3_pool(
            chain=chain_norm,
            protocol=proto_for_resolver,
            token_a=addr_a,
            token_b=addr_b,
            fee_bps=fee_bps,
        )
        if pool is None:
            # Fee-tier auto-discovery. PancakeSwap V3 / Uniswap V3 / Aerodrome
            # each support several tiers per pair (100 / 500 / 2500 / 10000
            # bps on PancakeSwap; 100 / 500 / 3000 / 10000 on Uniswap). When
            # the user-named tier has no pool, try the remaining tiers and
            # pick the highest-liquidity one so we never block on a default
            # fee mismatch (PancakeSwap BSC USDT-BNB has no 500bps pool but
            # a deep 2500bps pool exists).
            from src.data.v3_pool_resolver import list_fee_tiers_with_pools
            try:
                tiers = await list_fee_tiers_with_pools(
                    chain=chain_norm,
                    protocol=proto_for_resolver,
                    token_a=addr_a,
                    token_b=addr_b,
                )
            except Exception:
                tiers = []
            best: tuple[int, int] | None = None  # (fee_bps, liquidity)
            for t in tiers:
                cand_fee = int(getattr(t, "fee_bps", 0))
                cand_liq = int(getattr(t, "liquidity", 0) or 0)
                if cand_fee == fee_bps:
                    continue
                if best is None or cand_liq > best[1]:
                    best = (cand_fee, cand_liq)
            if best is not None:
                pool = await resolve_v3_pool(
                    chain=chain_norm,
                    protocol=proto_for_resolver,
                    token_a=addr_a,
                    token_b=addr_b,
                    fee_bps=best[0],
                )
                fee_bps = best[0]
            if pool is None:
                raise ValueError(
                    f"V3 NFT: no {request.protocol} pool for {sym_a}/{sym_b} on {request.chain} "
                    f"(tried fee {fee_bps}bps and any alternate tier with liquidity)."
                )

        # decimals map per resolved token0 / token1.
        # Hard requirement: both sides must resolve. The previous 18-decimal
        # fallback silently inflated USDC/USDT/WBTC mint amounts by 1e12 when
        # the RPC was unreachable — the resulting mint call always reverted
        # on-chain. Refuse to emit a step we know will fail.
        token0_meta = await resolve_any_evm_token(chain_norm, pool.token0)
        token1_meta = await resolve_any_evm_token(chain_norm, pool.token1)
        if not token0_meta or not token1_meta:
            raise ValueError(
                f"V3 NFT: could not resolve decimals for {pool.token0}/{pool.token1} on "
                f"{chain_norm}. Pool meta needed before emitting mint params; refusing to "
                "build a step that would revert."
            )
        decimals0 = token0_meta[1]
        decimals1 = token1_meta[1]

        # 2) Build tick range from preset or extra.
        lower_pct = float(extra.get("range_lower_pct") or -10.0)
        upper_pct = float(extra.get("range_upper_pct") or 10.0)
        tick_lower, tick_upper = tick_range_from_pct(
            pool.tick, lower_pct, upper_pct, pool.tick_spacing
        )

        # 3) USD price hints — V7-044: live DefiLlama oracle (60s cache) first,
        # tick-derived inversion second, last-resort static fallback third.
        # The static fallback exists only so a transient DefiLlama outage cannot
        # collapse amount0/amount1 to zero — the previous WETH=$2300 / WBTC=$80k
        # numbers were stale by months and produced wrong ratios in production.
        # Default of 1.0/1.0 produced garbage ratios for USDC/WETH (WETH at $1
        # vs $2300 collapsed amount1 to zero), hence the multi-tier resolution.
        _USD_FALLBACK = {
            "USDC": 1.0, "USDT": 1.0, "DAI": 1.0, "BUSD": 1.0, "FDUSD": 1.0,
            "TUSD": 1.0, "USDC.E": 1.0, "USDBC": 1.0, "USDE": 1.0, "SUSDE": 1.05,
            "SDAI": 1.04, "USDS": 1.0, "FRAX": 1.0, "LUSD": 1.0,
        }

        def _resolve_usd_hint(token_addr: str) -> float | None:
            meta_pair = (token0_meta, token1_meta)
            for meta in meta_pair:
                if not meta:
                    continue
                addr_l, _dec = meta
                if addr_l.lower() == token_addr.lower():
                    # No symbol stored in meta tuple; use reverse-symbol lookup
                    # via asset_registry mapping below.
                    break
            return None

        async def _symbol_for_addr(addr: str) -> str | None:
            for chain_key, sym in [(chain_norm, "USDC"), (chain_norm, "USDT"),
                                   (chain_norm, "DAI"), (chain_norm, "WETH"),
                                   (chain_norm, "WBTC"), (chain_norm, "STETH"),
                                   (chain_norm, "WSTETH"), (chain_norm, "RETH"),
                                   (chain_norm, "WBNB"), (chain_norm, "WMATIC"),
                                   (chain_norm, "WAVAX"), (chain_norm, "ARB"),
                                   (chain_norm, "AERO"), (chain_norm, "OP"),
                                   (chain_norm, "USDC.E"), (chain_norm, "USDBC")]:
                meta = await resolve_any_evm_token(chain_key, sym)
                if meta and meta[0].lower() == addr.lower():
                    return sym
            return None

        sym0 = await _symbol_for_addr(pool.token0)
        sym1 = await _symbol_for_addr(pool.token1)
        # Tick-derived price (token1 per token0 in human units).
        from src.data.v3_tick_math import price_from_tick
        tick_price = float(price_from_tick(pool.tick, decimals0, decimals1))

        price0 = extra.get("price_token0_usd")
        price1 = extra.get("price_token1_usd")
        # V7-044: query the live DefiLlama oracle for each side before falling
        # back to stable-coin = $1.0 hints or tick-derived inversion. Oracle
        # values are cached 60s in src/data/price_oracle.py so a 2-leg pool
        # build hits the network at most twice.
        if price0 is None or price1 is None:
            oracle = getattr(self, "price_oracle", None) or fetch_price_usd
            try:
                import aiohttp  # local import keeps cold-path overhead off hot calls
                async with aiohttp.ClientSession() as _sess:
                    if price0 is None:
                        price0 = await oracle(chain_norm, pool.token0, _sess)
                    if price1 is None:
                        price1 = await oracle(chain_norm, pool.token1, _sess)
            except Exception:
                # Oracle unreachable → fall through to symbol/tick fallback.
                pass
        if price0 is None and sym0 and sym0.upper() in _USD_FALLBACK:
            price0 = _USD_FALLBACK[sym0.upper()]
        if price1 is None and sym1 and sym1.upper() in _USD_FALLBACK:
            price1 = _USD_FALLBACK[sym1.upper()]
        # If only one side known, derive the other from tick price.
        if price0 is None and price1 is not None and tick_price > 0:
            price0 = float(price1) * tick_price
        if price1 is None and price0 is not None and tick_price > 0:
            price1 = float(price0) / tick_price
        if price0 is None:
            price0 = 1.0
        if price1 is None:
            price1 = 1.0
        price0 = float(price0)
        price1 = float(price1)

        # 4) Optimal ratio for selected range.
        ratio0, ratio1 = optimal_ratio_for_range(
            sqrt_price_x96_current=pool.sqrt_price_x96,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            decimals0=decimals0,
            decimals1=decimals1,
            price_token0_usd=price0,
            price_token1_usd=price1,
        )
        # Defensive guard against price-hint dropouts. When the current
        # tick is INSIDE [tick_lower, tick_upper] both legs are expected
        # to need non-trivial capital — a ratio that collapses to 0/1
        # (or 1/0) means symbol→USD hint lookup failed for one side and
        # the math fell back to 1.0/1.0 defaults, which made the math
        # ignore actual decimal scale. Detect that and re-derive both
        # prices from on-chain tick + a stable anchor so the swap step
        # never drains all input into one side.
        in_range = tick_lower < pool.tick < tick_upper
        if in_range and (ratio0 < Decimal("0.005") or ratio1 < Decimal("0.005")):
            anchor_sym = None
            if (sym0 or "").upper() in {"USDC", "USDT", "DAI", "FRAX", "USDS", "LUSD", "USDE", "USDC.E", "USDBC"}:
                anchor_sym = "token0"
            elif (sym1 or "").upper() in {"USDC", "USDT", "DAI", "FRAX", "USDS", "LUSD", "USDE", "USDC.E", "USDBC"}:
                anchor_sym = "token1"
            if anchor_sym and tick_price > 0:
                if anchor_sym == "token0":
                    price0 = 1.0
                    price1 = 1.0 / tick_price
                else:
                    price1 = 1.0
                    price0 = tick_price
                ratio0, ratio1 = optimal_ratio_for_range(
                    sqrt_price_x96_current=pool.sqrt_price_x96,
                    tick_lower=tick_lower,
                    tick_upper=tick_upper,
                    decimals0=decimals0,
                    decimals1=decimals1,
                    price_token0_usd=price0,
                    price_token1_usd=price1,
                )

        # 5) Input token metadata.
        in_meta = await resolve_any_evm_token(chain_norm, request.asset_in)
        if not in_meta:
            raise ValueError(f"V3 NFT: cannot resolve input token {request.asset_in}.")
        input_addr, input_dec = in_meta
        input_units_total = _to_units(request.amount_in, input_dec)

        # 6) Build steps.
        steps: list[ExecutionStepV3] = []
        deadline = int(time.time()) + 1200  # 20-min deadline

        # If input matches token0 — only swap into token1, and vice versa.
        # Otherwise swap input into both (two swap steps).
        input_addr_lc = input_addr.lower()
        is_input_token0 = input_addr_lc == pool.token0.lower()
        is_input_token1 = input_addr_lc == pool.token1.lower()

        if is_input_token0:
            need_swap_to_token0 = False
            need_swap_to_token1 = ratio1 > Decimal("0.001")
            swap0_units = 0
            swap1_units = int(Decimal(input_units_total) * ratio1)
        elif is_input_token1:
            need_swap_to_token0 = ratio0 > Decimal("0.001")
            need_swap_to_token1 = False
            swap0_units = int(Decimal(input_units_total) * ratio0)
            swap1_units = 0
        else:
            need_swap_to_token0 = ratio0 > Decimal("0.001")
            need_swap_to_token1 = ratio1 > Decimal("0.001")
            swap0_units = int(Decimal(input_units_total) * ratio0)
            swap1_units = int(Decimal(input_units_total) * ratio1)

        from src.routing.enso_client import EnsoClient
        enso = EnsoClient()

        step_idx = 1
        total_swap_legs = int(need_swap_to_token0 and swap0_units > 0) + int(
            need_swap_to_token1 and swap1_units > 0
        )
        swap_leg_emitted = 0
        sym0_label_swap = (sym0 or pool.token0[:6] + "…").upper()
        sym1_label_swap = (sym1 or pool.token1[:6] + "…").upper()

        def _leg_label() -> str:
            return f"leg {swap_leg_emitted}/{total_swap_legs}" if total_swap_legs > 1 else "swap"

        # --- Swap 1: input → token0 ---
        if need_swap_to_token0 and swap0_units > 0:
            try:
                rs = await enso.build(
                    chain_id=chain_id,
                    token_in=input_addr,
                    token_out=pool.token0,
                    amount_in=str(swap0_units),
                    from_addr=request.user_address,
                    slippage_bps=request.slippage_bps,
                )
                ut = rs.get("unsigned_tx") or {}
                swap_leg_emitted += 1
                leg_amount = Decimal(swap0_units) / Decimal(10 ** input_dec)
                steps.append(make_step(
                    index=step_idx,
                    action="swap",
                    title=f"Swap {request.asset_in} → {sym0_label_swap}",
                    description=(
                        f"Prep {_leg_label()} — swap {leg_amount} {request.asset_in} into "
                        f"{sym0_label_swap}."
                    ),
                    chain=request.chain,
                    wallet="MetaMask",
                    protocol=request.protocol,
                    asset_in=request.asset_in,
                    amount_in=str(leg_amount),
                    asset_out=sym0_label_swap,
                    slippage_bps=request.slippage_bps,
                    gas_estimate_usd=3.0,
                    duration_estimate_s=30,
                    transaction=UnsignedStepTransaction(
                        chain_kind="evm",
                        chain_id=chain_id,
                        to=ut.get("to"),
                        data=ut.get("data"),
                        value=str(ut.get("value", "0x0")),
                        spender=ut.get("to"),
                    ),
                    risk_warnings=["Enso router auto-handles input token approval via Permit2."],
                ))
                step_idx += 1
            except Exception as exc:
                raise ValueError(f"V3 NFT: Enso swap input→token0 failed: {exc}") from exc

        # --- Swap 2: input → token1 ---
        if need_swap_to_token1 and swap1_units > 0:
            try:
                rs = await enso.build(
                    chain_id=chain_id,
                    token_in=input_addr,
                    token_out=pool.token1,
                    amount_in=str(swap1_units),
                    from_addr=request.user_address,
                    slippage_bps=request.slippage_bps,
                )
                ut = rs.get("unsigned_tx") or {}
                swap_leg_emitted += 1
                leg_amount = Decimal(swap1_units) / Decimal(10 ** input_dec)
                steps.append(make_step(
                    index=step_idx,
                    action="swap",
                    title=f"Swap {request.asset_in} → {sym1_label_swap}",
                    description=(
                        f"Prep {_leg_label()} — swap {leg_amount} {request.asset_in} into "
                        f"{sym1_label_swap}."
                    ),
                    chain=request.chain,
                    wallet="MetaMask",
                    protocol=request.protocol,
                    asset_in=request.asset_in,
                    amount_in=str(leg_amount),
                    asset_out=sym1_label_swap,
                    slippage_bps=request.slippage_bps,
                    gas_estimate_usd=3.0,
                    duration_estimate_s=30,
                    transaction=UnsignedStepTransaction(
                        chain_kind="evm",
                        chain_id=chain_id,
                        to=ut.get("to"),
                        data=ut.get("data"),
                        value=str(ut.get("value", "0x0")),
                        spender=ut.get("to"),
                    ),
                    risk_warnings=["Enso router auto-handles input token approval via Permit2."],
                ))
                step_idx += 1
            except Exception as exc:
                raise ValueError(f"V3 NFT: Enso swap input→token1 failed: {exc}") from exc

        # Estimated amounts the mint will pull. Side A is what the user
        # keeps (input minus what they swap to the other side); side B is
        # the swap-out estimate (compute from USD value + price).
        # Input USD total (use price of side that user supplies natively).
        input_usd_total = Decimal(input_units_total) / (Decimal(10) ** input_dec)
        if is_input_token0:
            input_usd_total *= Decimal(price0)
        elif is_input_token1:
            input_usd_total *= Decimal(price1)
        else:
            # Foreign-token input — assume input token is priced like USDC.
            input_usd_total *= Decimal(1)

        usd_for_token0 = input_usd_total * ratio0
        usd_for_token1 = input_usd_total * ratio1

        amount0_desired = int(
            usd_for_token0 * (Decimal(10) ** decimals0) / Decimal(price0 or 1.0)
        )
        amount1_desired = int(
            usd_for_token1 * (Decimal(10) ** decimals1) / Decimal(price1 or 1.0)
        )
        # Override side held natively: user kept (input - swap_out_side).
        if is_input_token0:
            amount0_desired = max(input_units_total - swap1_units, amount0_desired)
        if is_input_token1:
            amount1_desired = max(input_units_total - swap0_units, amount1_desired)

        # Spec §11 / D.3: scope each approval to exactly what the mint
        # consumes, plus a 5% slippage buffer for tick-rounding drift.
        # No unlimited approve. Permit2 path lands in a follow-up; this
        # path remains a raw approve() because Permit2 needs typed-data
        # signing wired through the frontend.
        approve0_amount = amount0_desired + (amount0_desired // 20)
        approve1_amount = amount1_desired + (amount1_desired // 20)

        sym0_lbl = (sym0 or pool.token0[:6] + "…").upper()
        sym1_lbl = (sym1 or pool.token1[:6] + "…").upper()

        # Approve token0 → NFP manager
        steps.append(make_step(
            index=step_idx,
            action="approve",
            title=f"Approve {sym0_lbl} to position manager",
            description=(
                f"Scoped approve so the {request.protocol} position manager can pull up to "
                f"{approve0_amount} units of {sym0_lbl} for this mint (deposit + 5% buffer)."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=sym0_lbl,
            amount_in=str(approve0_amount),
            slippage_bps=0,
            gas_estimate_usd=1.5,
            duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=pool.token0,
                data=_encode_approve(pool.nfp_manager, approve0_amount),
                value="0x0",
                spender=pool.nfp_manager,
            ),
        ))
        step_idx += 1

        # Approve token1 → NFP manager
        steps.append(make_step(
            index=step_idx,
            action="approve",
            title=f"Approve {sym1_lbl} to position manager",
            description=(
                f"Scoped approve so the {request.protocol} position manager can pull up to "
                f"{approve1_amount} units of {sym1_lbl} for this mint (deposit + 5% buffer)."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=sym1_lbl,
            amount_in=str(approve1_amount),
            slippage_bps=0,
            gas_estimate_usd=1.5,
            duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=pool.token1,
                data=_encode_approve(pool.nfp_manager, approve1_amount),
                value="0x0",
                spender=pool.nfp_manager,
            ),
        ))
        step_idx += 1

        # Mint position
        slippage_factor = (10_000 - max(request.slippage_bps, 50)) / 10_000.0
        amount0_min = int(amount0_desired * slippage_factor)
        amount1_min = int(amount1_desired * slippage_factor)
        mint_params = _encode_mint_params(
            token0=pool.token0,
            token1=pool.token1,
            fee=pool.fee_bps,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            amount0_desired=amount0_desired,
            amount1_desired=amount1_desired,
            amount0_min=amount0_min,
            amount1_min=amount1_min,
            recipient=request.user_address,
            deadline=deadline,
        )
        mint_call = _encode_mint_call(mint_params)

        # Prefer human symbols (USDC, WETH) in the asset_in field and step
        # description so the chat row doesn't surface raw addresses like
        # "0xa0b869+0xc02aaa" to the tester. Fall back to truncated addresses
        # only when symbol lookup misses for an exotic pool.
        sym0_label = (sym0 or pool.token0[:6] + "…").upper()
        sym1_label = (sym1 or pool.token1[:6] + "…").upper()
        steps.append(make_step(
            index=step_idx,
            action="deposit_lp",
            title=f"Open V3 position [{lower_pct:+.0f}% / {upper_pct:+.0f}%]",
            description=(
                f"Mint NFT position in {request.protocol} {sym0_label}/{sym1_label} "
                f"{fee_bps/10000:.2f}% fee tier. Range ticks {tick_lower} → {tick_upper} (spacing {pool.tick_spacing}). "
                f"Desired: amount0={amount0_desired}, amount1={amount1_desired}. "
                f"Min: amount0={amount0_min}, amount1={amount1_min}. "
                f"Recipient: {request.user_address}, deadline={deadline}."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            # Surface the user's original input symbol (singular) — the
            # mint internally pulls token0+token1 but the WALLET needs to
            # start with `request.amount_in` of `request.asset_in`. A
            # compound "USDC+WETH" asset_in confuses the totals roll-up.
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"{request.protocol}-position-nft",
            slippage_bps=request.slippage_bps,
            gas_estimate_usd=6.0,
            duration_estimate_s=30,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=pool.nfp_manager,
                data=mint_call,
                value="0x0",
                spender=pool.nfp_manager,
            ),
            risk_warnings=[
                f"Position NFT minted to {request.user_address}. Save the returned tokenId from the tx receipt.",
                f"Range covers ticks {tick_lower}…{tick_upper}; goes out-of-range if {sym0_label}/{sym1_label} price exits this band.",
            ],
        ))
        step_idx += 1

        # V7-048 — optional CLGauge.deposit(tokenId) leg. Defaults to False
        # so existing callers keep their LP NFT in-wallet and collect fees
        # only. When stake_in_gauge=True AND the protocol exposes a gauge
        # (Aerodrome Slipstream / Velodrome CL), append a second step that
        # transfers the freshly-minted NFT into the gauge contract for
        # emissions accrual. The tokenId is unknown at build time (returned
        # by the mint receipt), so we emit a templated calldata that the
        # broker layer rewrites with the real id after the mint confirms —
        # marked with a `needs_token_id_rewrite` flag in step extras.
        stake_in_gauge = bool(extra.get("stake_in_gauge") or False)
        if stake_in_gauge and proto_norm in _GAUGED_PROTOCOLS:
            gauge_addr = _resolve_gauge_address(proto_norm, pool.nfp_manager)
            # Placeholder tokenId = 0; broker substitutes the real id after
            # the mint receipt parses the NonfungiblePositionManager
            # Transfer(from=0x0, to=user, tokenId) log.
            placeholder_token_id = 0
            stake_data = _encode_gauge_deposit(placeholder_token_id)
            steps.append(make_step(
                index=step_idx,
                action="stake",
                title=f"Stake {request.protocol} LP NFT in CL gauge",
                description=(
                    f"Transfer the freshly-minted V3 position NFT into the {request.protocol} "
                    f"CL gauge at {gauge_addr} to start accruing emission rewards on top of "
                    f"swap-fee accrual. Broker rewrites tokenId after mint confirms."
                ),
                chain=request.chain,
                wallet="MetaMask",
                protocol=request.protocol,
                asset_in=f"{request.protocol}-position-nft",
                amount_in="1",
                asset_out=f"{request.protocol}-gauge-stake",
                slippage_bps=0,
                gas_estimate_usd=2.5,
                duration_estimate_s=20,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm",
                    chain_id=chain_id,
                    to=gauge_addr,
                    data=stake_data,
                    value="0x0",
                    spender=gauge_addr,
                ),
                risk_warnings=[
                    "Staked NFT lives in the gauge — must call gauge.withdraw(tokenId) before closing the position.",
                    "Emission rewards accrue in the protocol's reward token (e.g., AERO/VELO); claim separately via gauge.getReward().",
                    "Placeholder tokenId in calldata — broker substitutes real id from mint receipt before broadcast.",
                ],
            ))

        return steps

    async def _build_lifecycle(
        self,
        *,
        chain: str,
        chain_id: int,
        protocol: str,
        action: str,
        extra: dict[str, Any],
        user_address: str,
    ) -> list[ExecutionStepV3]:
        """Phase 4 — decrease_liquidity / collect / close_position on the
        NonfungiblePositionManager. Caller supplies the existing tokenId
        + liquidity to remove via extra; this builder encodes a multicall
        of decreaseLiquidity + collect (+ burn for close).
        """
        import time
        from src.data.v3_pool_resolver import V3_FACTORIES
        cfg = V3_FACTORIES.get((chain, protocol))
        if not cfg or not cfg.get("nfp_manager"):
            raise ValueError(
                f"No NonfungiblePositionManager registered for ({chain}, {protocol})."
            )
        nfp = cfg["nfp_manager"]
        token_id_raw = extra.get("token_id") or extra.get("tokenId")
        if token_id_raw is None:
            raise ValueError("Lifecycle action requires extra.token_id.")
        token_id = int(token_id_raw)
        liquidity = int(extra.get("liquidity") or 0)
        if action != "collect" and liquidity <= 0:
            raise ValueError("Lifecycle decrease_liquidity / close requires extra.liquidity > 0.")
        amount0_min = int(extra.get("amount0_min") or 0)
        amount1_min = int(extra.get("amount1_min") or 0)
        deadline = int(time.time()) + 30 * 60
        recipient = user_address

        calls: list[str] = []
        # decreaseLiquidity((tokenId, liquidity, amount0Min, amount1Min, deadline))
        if action in {"decrease_liquidity", "close_position"} and liquidity > 0:
            params = (
                _enc_uint(token_id)
                + _enc_uint(liquidity)
                + _enc_uint(amount0_min)
                + _enc_uint(amount1_min)
                + _enc_uint(deadline)
            )
            calls.append(_DECREASE_LIQ_SEL + params)
        # collect((tokenId, recipient, amount0Max=uint128.max, amount1Max=uint128.max))
        u128_max = (1 << 128) - 1
        collect_params = (
            _enc_uint(token_id)
            + _enc_addr(recipient)
            + _enc_uint(u128_max)
            + _enc_uint(u128_max)
        )
        calls.append(_COLLECT_SEL + collect_params)
        # burn(tokenId) — close only.
        if action == "close_position":
            calls.append(_BURN_SEL + _enc_uint(token_id))

        # Multicall(bytes[]) — inner calldata is hex strings prefixed with the
        # selector "0x...". Strip the 0x before length / padding math.
        n = len(calls)
        offsets: list[str] = []
        cursor = 32 * n
        bodies: list[str] = []
        for c in calls:
            c_hex = c.removeprefix("0x")
            cb = bytes.fromhex(c_hex)
            offsets.append(_enc_uint(cursor))
            body_padded = c_hex.ljust(((len(cb) + 31) // 32) * 64, "0")
            bodies.append(_enc_uint(len(cb)) + body_padded)
            cursor += 32 + ((len(cb) + 31) // 32) * 32
        multicall_inner = _enc_uint(n) + "".join(offsets) + "".join(bodies)
        # multicall(bytes[]) head: offset 32
        multicall_data = _MULTICALL_SEL + _enc_uint(32) + multicall_inner

        title_map = {
            "decrease_liquidity": "Decrease V3 position",
            "collect": "Collect V3 fees",
            "close_position": "Close V3 position",
        }
        desc_map = {
            "decrease_liquidity": (
                f"Decrease liquidity by {liquidity} on tokenId {token_id} via "
                f"{protocol} NFP {nfp}. Recipient {recipient}."
            ),
            "collect": (
                f"Collect uncollected fees on tokenId {token_id} via "
                f"{protocol} NFP {nfp}. Recipient {recipient}."
            ),
            "close_position": (
                f"Close position tokenId {token_id} — decrease 100% + collect + burn — "
                f"via {protocol} NFP {nfp}. Recipient {recipient}."
            ),
        }
        return [
            make_step(
                index=1, action=action,
                title=title_map[action],
                description=desc_map[action],
                chain=chain, wallet="MetaMask", protocol=protocol,
                asset_in=None, amount_in=None,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=nfp, data=multicall_data, value="0x0", spender=nfp,
                ),
                gas_estimate_usd=4.0, duration_estimate_s=30,
                risk_warnings=[
                    f"NFP multicall: {len(calls)} inner call(s). Tx fails if any sub-call reverts.",
                    "Collected fees + decreased liquidity land in your wallet.",
                ],
            ),
        ]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(confirmed=False, detail="V3 NFT receipt verify: read NonfungiblePositionManager.Transfer log for tokenId.")
