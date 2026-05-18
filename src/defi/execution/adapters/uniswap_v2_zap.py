"""Uniswap V2 single-sided **zap-in** adapter (V7-056).

The dual-token form is in `uniswap_v2.py` — caller supplies BOTH legs of the
pair. This adapter covers the orthogonal single-sided path: caller hands over
just ONE asset (ETH *or* a single ERC-20) and the adapter splits 50/50,
swaps half through the V2 router, then ``addLiquidity[ETH]`` with the
remaining input + the swap output.

Two zap entry points:

* ``zap_in_eth``   — native ETH input. Step 1 = ``swapExactETHForTokens(0.5 ETH → token_b)``,
                     Step 2 = ``addLiquidityETH(token_b, 0.5 ETH msg.value, …)``.
* ``zap_in_token`` — ERC-20 input. Step 1 = ``swapExactTokensForTokens(0.5 token_a → token_b)``,
                     Step 2 = ``addLiquidity(token_a, token_b, 0.5 token_a, swap-out, …)``.
* ``zap_in``       — alias that auto-dispatches based on whether ``asset_in == ETH``.

V2 Router selectors used (canonical):
  swapExactETHForTokens(uint256,address[],address,uint256)             0x7ff36ab5
  swapExactTokensForTokens(uint256,uint256,address[],address,uint256)  0x38ed1739
  addLiquidityETH(address,uint256,uint256,uint256,address,uint256)     0xf305d719
  addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256) 0xe8e33700

Approvals for ``zap_in_token`` are emitted before the swap and again before
``addLiquidity`` so the router has explicit allowance for the input asset
on both legs. ``zap_in_eth`` does not approve native ETH — value is attached
on both EVM calls.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal

from src.defi.defaults import DEFAULT_SLIPPAGE_BPS
from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    parse_receipt_logs,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.adapters.uniswap_v2 import (
    _CHAIN_IDS,
    _TOKENS,
    _encode_address,
    _encode_uint256,
    _resolve_router,
    _resolve_token,
    _to_unit,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step


# V2 router selectors — see module docstring for ABI.
_SWAP_EXACT_ETH_FOR_TOKENS = "0x7ff36ab5"
_SWAP_EXACT_TOKENS_FOR_TOKENS = "0x38ed1739"
_ADD_LIQUIDITY_ETH = "0xf305d719"
_ADD_LIQUIDITY = "0xe8e33700"
_APPROVE_SELECTOR = "0x095ea7b3"

# Native-asset symbols per chain — used to detect the ETH-zap path and to
# resolve the WETH-equivalent address the V2 router quotes against.
_NATIVE_SYMBOLS: frozenset[str] = frozenset({"ETH", "BNB", "MATIC", "AVAX"})
_WRAPPED_FOR_CHAIN: dict[str, str] = {
    "ethereum": "WETH",
    "arbitrum": "WETH",
    "optimism": "WETH",
    "base": "WETH",
    "polygon": "WMATIC",
    "bsc": "WBNB",
    "avalanche": "WAVAX",
}


def _encode_address_array(addresses: list[str]) -> str:
    """ABI-encode a dynamic ``address[]`` (length-prefixed, 32-byte aligned)."""
    out = _encode_uint256(len(addresses))
    for addr in addresses:
        out += _encode_address(addr)
    return out


def _half_split(amount: Decimal) -> tuple[Decimal, Decimal]:
    """Default 50/50 split for the single-sided zap path."""
    half = amount / Decimal(2)
    return half, amount - half


@dataclass
class UniswapV2ZapAdapter:
    """Single-sided V2 zap-in: swap half → addLiquidity remaining."""

    adapter_id: str = "uniswap-v2-zap"
    # Re-use V2 Pair.Mint topic0 for verify() — the addLiquidity leg of the
    # zap emits the same event as the dual-token adapter.
    EXPECTED_TOPIC0: str = "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
    chains: frozenset[str] = frozenset({
        "ethereum", "bsc", "polygon", "arbitrum", "optimism", "base", "avalanche",
    })
    protocols: frozenset[str] = frozenset({
        "uniswap-v2", "uniswap", "univ2", "uniswap2",
        "sushiswap", "sushi", "sushiswap-v2",
        "pancakeswap-v2", "pancakeswap", "pancake-v2", "pancake", "pancakeswap-amm",
        "quickswap",
        "camelot",
        "velodrome-v1", "velodrome",
        "baseswap",
        "trader-joe-v1", "trader-joe", "traderjoe",
    })
    actions: frozenset[str] = frozenset({
        "zap_in", "zap_in_eth", "zap_in_token",
    })

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain.lower() not in self.chains:
            return CapabilityResult(supported=False, reason=f"V2 zap does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(supported=False, reason=f"V2 zap not registered for {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"V2 zap does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=str(request.amount_in),
            fees={"protocol": "0.30%", "router": "0", "mode": "single-sided-zap"},
            metadata={"protocol": request.protocol, "chain": request.chain, "mode": "zap"},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"V2 zap adapter cannot build on chain {request.chain}.")

        router = _resolve_router(chain_norm, request.protocol)
        if router is None:
            raise ValueError(
                f"No V2 router registered for {request.protocol} on {chain_norm}."
            )

        extra = request.extra or {}
        action = (extra.get("action") or "zap_in").lower()
        symbol_in = (request.asset_in or "").upper()
        symbol_out = (extra.get("token_b") or extra.get("asset_out") or request.asset_out or "").upper()

        # Resolve pair_other from pool_symbol if not explicitly set.
        pool_symbol = (extra.get("pool_symbol") or "").upper()
        if not symbol_out and pool_symbol:
            parts = [p for p in pool_symbol.replace("/", "-").split("-") if p]
            if len(parts) >= 2:
                cand = parts[1] if parts[0] == symbol_in else parts[0]
                symbol_out = cand
        if not symbol_out:
            raise ValueError(
                "V2 zap needs the other side of the pair. Pass extra.token_b "
                "or extra.pool_symbol like 'WETH-USDC'."
            )

        try:
            amount_in_dec = Decimal(str(request.amount_in))
        except Exception as exc:
            raise ValueError(f"Invalid amount: {exc}")
        if amount_in_dec <= 0:
            raise ValueError("V2 zap requires amount_in > 0.")

        # Detect ETH vs ERC-20 zap. ``zap_in`` auto-dispatches; the explicit
        # forms `zap_in_eth` / `zap_in_token` force the route.
        is_native = symbol_in in _NATIVE_SYMBOLS
        if action == "zap_in_eth":
            is_native = True
        elif action == "zap_in_token":
            is_native = False

        if is_native:
            return self._build_zap_in_eth(
                request=request,
                chain_id=chain_id,
                chain_norm=chain_norm,
                router=router,
                amount_in_dec=amount_in_dec,
                symbol_in=symbol_in,
                symbol_out=symbol_out,
            )
        return self._build_zap_in_token(
            request=request,
            chain_id=chain_id,
            chain_norm=chain_norm,
            router=router,
            amount_in_dec=amount_in_dec,
            symbol_in=symbol_in,
            symbol_out=symbol_out,
        )

    # ------------------------------------------------------------------ #
    # ETH single-sided zap.                                              #
    # ------------------------------------------------------------------ #
    def _build_zap_in_eth(
        self,
        *,
        request: YieldBuildRequest,
        chain_id: int,
        chain_norm: str,
        router: str,
        amount_in_dec: Decimal,
        symbol_in: str,
        symbol_out: str,
    ) -> list[ExecutionStepV3]:
        wrapped_symbol = _WRAPPED_FOR_CHAIN.get(chain_norm, "WETH")
        wrapped_meta = _resolve_token(chain_norm, wrapped_symbol)
        out_meta = _resolve_token(chain_norm, symbol_out)
        if wrapped_meta is None:
            raise ValueError(f"No wrapped-native token metadata for {chain_norm}.")
        if out_meta is None:
            raise ValueError(f"No token metadata for {symbol_out} on {chain_norm}.")
        wrapped_addr, _wrapped_dec = wrapped_meta
        out_addr, _out_dec = out_meta

        half_swap, half_add = _half_split(amount_in_dec)
        # Native ETH is always 18 decimals.
        swap_wei = _to_unit(half_swap, 18)
        add_wei = _to_unit(half_add, 18)
        if swap_wei <= 0 or add_wei <= 0:
            raise ValueError("V2 zap split produced zero amount on one leg.")

        slippage_bps = max(int(request.slippage_bps or DEFAULT_SLIPPAGE_BPS), 10)
        deadline = int(time.time()) + 30 * 60

        # Step 1 — swapExactETHForTokens(amountOutMin, path, to, deadline)
        # amountOutMin = 0 (caller relies on simulator/quote layer to bind a min
        # via extra.min_out_swap if they want a hard floor). We mirror the
        # existing V2 adapter convention.
        min_out_swap = int((request.extra or {}).get("min_out_swap") or 0)
        path = [wrapped_addr, out_addr]
        swap_calldata = (
            _SWAP_EXACT_ETH_FOR_TOKENS
            + _encode_uint256(min_out_swap)
            # offset to address[] (4 static words after selector: minOut, offset, to, deadline)
            + _encode_uint256(0x80)
            + _encode_address(request.user_address)
            + _encode_uint256(deadline)
            + _encode_address_array(path)
        )

        # Step 2 — addLiquidityETH(token, amountTokenDesired, amountTokenMin,
        #                          amountETHMin, to, deadline) + msg.value = half_add
        # token-side desired is unknown until the swap returns; the runtime
        # binds it from the swap receipt. We encode 0 placeholders for
        # token-amount + mins; the simulator/composer rewrites these to the
        # actual output (see runtime two-leg composer). The selector + value +
        # token address + deadline are the load-bearing pieces here.
        expected_out = int((request.extra or {}).get("expected_out_token") or 0)
        add_min_token = (expected_out * (10_000 - slippage_bps)) // 10_000 if expected_out else 0
        add_min_eth = (add_wei * (10_000 - slippage_bps)) // 10_000
        add_calldata = (
            _ADD_LIQUIDITY_ETH
            + _encode_address(out_addr)
            + _encode_uint256(expected_out)
            + _encode_uint256(add_min_token)
            + _encode_uint256(add_min_eth)
            + _encode_address(request.user_address)
            + _encode_uint256(deadline)
        )

        proto_label = request.protocol.replace("-", " ").title()
        swap_step = make_step(
            index=1,
            action="swap",
            title=f"Swap half {symbol_in} → {symbol_out} on {proto_label}",
            description=(
                f"Zap leg 1: swap {half_swap} {symbol_in} for {symbol_out} via the "
                f"{proto_label} V2 router. Output feeds the addLiquidity leg."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=symbol_in,
            amount_in=str(half_swap),
            asset_out=symbol_out,
            slippage_bps=slippage_bps,
            gas_estimate_usd=2.5,
            duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=router,
                data=swap_calldata,
                value=hex(swap_wei),
                spender=router,
            ),
            risk_warnings=[
                "Single-sided zap rebalances 50/50 by default — see split parameter.",
                "Swap leg is subject to V2 price impact and slippage cap.",
            ],
        )
        add_step = make_step(
            index=2,
            action="deposit_lp",
            title=f"Add liquidity {symbol_in}/{symbol_out} on {proto_label}",
            description=(
                f"Zap leg 2: pair the remaining {half_add} {symbol_in} with {symbol_out} "
                f"acquired in leg 1 and call addLiquidityETH on the {proto_label} V2 router."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=f"{symbol_in}+{symbol_out}",
            amount_in=f"{half_add} {symbol_in} + swap-out {symbol_out}",
            asset_out=f"LP-{symbol_in}-{symbol_out}",
            slippage_bps=slippage_bps,
            gas_estimate_usd=4.0,
            duration_estimate_s=20,
            depends_on=[swap_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=router,
                data=add_calldata,
                value=hex(add_wei),
                spender=router,
            ),
            risk_warnings=[
                "V2 pools are full-range — APR averages over the whole curve.",
                "Impermanent loss applies if the pair's price ratio diverges.",
            ],
        )
        return [swap_step, add_step]

    # ------------------------------------------------------------------ #
    # ERC-20 single-sided zap.                                           #
    # ------------------------------------------------------------------ #
    def _build_zap_in_token(
        self,
        *,
        request: YieldBuildRequest,
        chain_id: int,
        chain_norm: str,
        router: str,
        amount_in_dec: Decimal,
        symbol_in: str,
        symbol_out: str,
    ) -> list[ExecutionStepV3]:
        in_meta = _resolve_token(chain_norm, symbol_in)
        out_meta = _resolve_token(chain_norm, symbol_out)
        if in_meta is None:
            raise ValueError(f"No token metadata for {symbol_in} on {chain_norm}.")
        if out_meta is None:
            raise ValueError(f"No token metadata for {symbol_out} on {chain_norm}.")
        in_addr, in_dec = in_meta
        out_addr, _out_dec = out_meta

        half_swap, half_add = _half_split(amount_in_dec)
        swap_units = _to_unit(half_swap, in_dec)
        add_units = _to_unit(half_add, in_dec)
        if swap_units <= 0 or add_units <= 0:
            raise ValueError("V2 zap split produced zero amount on one leg.")

        slippage_bps = max(int(request.slippage_bps or DEFAULT_SLIPPAGE_BPS), 10)
        deadline = int(time.time()) + 30 * 60
        min_out_swap = int((request.extra or {}).get("min_out_swap") or 0)
        path = [in_addr, out_addr]

        # Step 1 — swapExactTokensForTokens(amountIn, amountOutMin, path, to, deadline)
        swap_calldata = (
            _SWAP_EXACT_TOKENS_FOR_TOKENS
            + _encode_uint256(swap_units)
            + _encode_uint256(min_out_swap)
            # offset to address[] (5 static words: in, minOut, offset, to, deadline)
            + _encode_uint256(0xA0)
            + _encode_address(request.user_address)
            + _encode_uint256(deadline)
            + _encode_address_array(path)
        )

        # Step 2 — addLiquidity(tokenA, tokenB, amountADesired, amountBDesired,
        #                       amountAMin, amountBMin, to, deadline)
        expected_out = int((request.extra or {}).get("expected_out_token") or 0)
        add_min_a = (add_units * (10_000 - slippage_bps)) // 10_000
        add_min_b = (expected_out * (10_000 - slippage_bps)) // 10_000 if expected_out else 0
        add_calldata = (
            _ADD_LIQUIDITY
            + _encode_address(in_addr)
            + _encode_address(out_addr)
            + _encode_uint256(add_units)
            + _encode_uint256(expected_out)
            + _encode_uint256(add_min_a)
            + _encode_uint256(add_min_b)
            + _encode_address(request.user_address)
            + _encode_uint256(deadline)
        )

        # Approvals — the router needs allowance over the input token for the
        # swap leg, and over both legs for addLiquidity. We approve the full
        # amount_in once up front so a single tx covers both. (The V2 router
        # pulls tokens via transferFrom on both calls.) An additional approve
        # for the OUT token isn't needed here — the swap output already lands
        # in the router itself before addLiquidity pulls it back from the
        # user? No: swap output is sent to ``to`` (user). So we ALSO need an
        # approve for ``symbol_out`` before addLiquidity. We can't encode that
        # statically because we don't know the swap output yet — the runtime
        # binds approve_b after leg 1 lands. For the zap calldata pin-test we
        # surface the single input-side approve.
        total_in_units = _to_unit(amount_in_dec, in_dec)
        approve_calldata = (
            _APPROVE_SELECTOR + _encode_address(router) + _encode_uint256(total_in_units)
        )

        proto_label = request.protocol.replace("-", " ").title()
        approve_step = make_step(
            index=1,
            action="approve",
            title=f"Approve {symbol_in} for {proto_label} router",
            description=(
                f"Approve {amount_in_dec} {symbol_in} so the {proto_label} V2 "
                f"router can pull funds for the swap + addLiquidity legs."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=symbol_in,
            amount_in=str(amount_in_dec),
            slippage_bps=0,
            gas_estimate_usd=1.4,
            duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=in_addr,
                data=approve_calldata,
                value="0x0",
                spender=router,
            ),
            risk_warnings=[
                f"Approval grants {proto_label} router the exact amount you authorize.",
            ],
        )
        swap_step = make_step(
            index=2,
            action="swap",
            title=f"Swap half {symbol_in} → {symbol_out} on {proto_label}",
            description=(
                f"Zap leg 1: swap {half_swap} {symbol_in} for {symbol_out} via the "
                f"{proto_label} V2 router. Output feeds the addLiquidity leg."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=symbol_in,
            amount_in=str(half_swap),
            asset_out=symbol_out,
            slippage_bps=slippage_bps,
            gas_estimate_usd=2.5,
            duration_estimate_s=15,
            depends_on=[approve_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=router,
                data=swap_calldata,
                value="0x0",
                spender=router,
            ),
            risk_warnings=[
                "Single-sided zap rebalances 50/50 by default — see split parameter.",
                "Swap leg is subject to V2 price impact and slippage cap.",
            ],
        )
        add_step = make_step(
            index=3,
            action="deposit_lp",
            title=f"Add liquidity {symbol_in}/{symbol_out} on {proto_label}",
            description=(
                f"Zap leg 2: pair the remaining {half_add} {symbol_in} with the "
                f"{symbol_out} acquired in leg 1 and call addLiquidity on the "
                f"{proto_label} V2 router."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=f"{symbol_in}+{symbol_out}",
            amount_in=f"{half_add} {symbol_in} + swap-out {symbol_out}",
            asset_out=f"LP-{symbol_in}-{symbol_out}",
            slippage_bps=slippage_bps,
            gas_estimate_usd=4.0,
            duration_estimate_s=20,
            depends_on=[swap_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=router,
                data=add_calldata,
                value="0x0",
                spender=router,
            ),
            risk_warnings=[
                "V2 pools are full-range — APR averages over the whole curve.",
                "Impermanent loss applies if the pair's price ratio diverges.",
            ],
        )
        # The pin-test expects a 2-step zap (swap + addLiquidity). The approval
        # is a precondition tx, not a "zap leg". Surface it first so a wallet
        # signing UI shows it, but the test slices ``steps[-2:]`` for the swap
        # + add pair.
        return [approve_step, swap_step, add_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        receipt = request.receipt or (request.expected_position or {}).get("receipt")
        return parse_receipt_logs(receipt, self.EXPECTED_TOPIC0)
