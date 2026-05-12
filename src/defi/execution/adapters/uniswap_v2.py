"""Uniswap V2 (and V2 forks) dual-token addLiquidity adapter (Phase 7 baseline).

User provides BOTH sides of the pair (e.g. "100 USDC and 0.05 WETH").
Single-sided V2 zap (swap half then add) requires an off-chain quote and
ships in a follow-up phase. The dual-token form is the one we deterministically
build here: three signed steps — approve tokenA, approve tokenB, addLiquidity.

V2 Router ABI:
  addLiquidity(address tokenA, address tokenB,
               uint amountADesired, uint amountBDesired,
               uint amountAMin, uint amountBMin,
               address to, uint deadline)
  selector: 0xe8e33700
"""
from __future__ import annotations

import time
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


_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "bsc": 56,
}

# (chain, protocol_slug) -> Router contract.
_V2_ROUTERS: dict[tuple[str, str], str] = {
    ("ethereum", "uniswap-v2"): "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
    ("ethereum", "sushiswap"): "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
    ("bsc", "pancakeswap-v2"): "0x10ED43C718714eb63d5aA57B78B54704E256024E",
    ("bsc", "pancakeswap"): "0x10ED43C718714eb63d5aA57B78B54704E256024E",
    ("polygon", "quickswap"): "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
    ("polygon", "sushiswap"): "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
    ("arbitrum", "sushiswap"): "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
    ("arbitrum", "camelot"): "0xc873fEcbd354f5A56E00E710B90EF4201db2448d",
    ("optimism", "sushiswap"): "0x2ABf469074dc0b54d793850807E6eb5Faf2625b1",
    ("optimism", "velodrome-v1"): "0xa132DAB612dB5cB9fC9Ac426A0Cc215A3423F9c9",
    ("base", "sushiswap"): "0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891",
    ("base", "baseswap"): "0x327Df1E6de05895d2ab08513aaDD9313Fe505d86",
    ("avalanche", "trader-joe-v1"): "0x60aE616a2155Ee3d9A68541Ba4544862310933d4",
    ("avalanche", "sushiswap"): "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
}

# (chain, symbol) -> (address, decimals). Keep this aligned with the Aave V3
# adapter's _ASSETS — they describe the same tokens.
_TOKENS: dict[tuple[str, str], tuple[str, int]] = {
    # Ethereum
    ("ethereum", "USDC"): ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    ("ethereum", "USDT"): ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    ("ethereum", "DAI"): ("0x6b175474e89094c44da98b954eedeac495271d0f", 18),
    ("ethereum", "WETH"): ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
    ("ethereum", "WBTC"): ("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 8),
    # BSC
    ("bsc", "USDC"): ("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", 18),
    ("bsc", "USDT"): ("0x55d398326f99059ff775485246999027b3197955", 18),
    ("bsc", "WBNB"): ("0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", 18),
    ("bsc", "BNB"): ("0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", 18),
    ("bsc", "WETH"): ("0x2170ed0880ac9a755fd29b2688956bd959f933f8", 18),
    ("bsc", "BUSD"): ("0xe9e7cea3dedca5984780bafc599bd69add087d56", 18),
    # Polygon
    ("polygon", "USDC"): ("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", 6),
    ("polygon", "USDT"): ("0xc2132d05d31c914a87c6611c10748aeb04b58e8f", 6),
    ("polygon", "DAI"): ("0x8f3cf7ad23cd3cadbd9735aff958023239c6a063", 18),
    ("polygon", "WMATIC"): ("0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270", 18),
    ("polygon", "WETH"): ("0x7ceb23fd6bc0add59e62ac25578270cff1b9f619", 18),
    # Arbitrum
    ("arbitrum", "USDC"): ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", 6),
    ("arbitrum", "USDT"): ("0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", 6),
    ("arbitrum", "WETH"): ("0x82af49447d8a07e3bd95bd0d56f35241523fbab1", 18),
    ("arbitrum", "ARB"): ("0x912ce59144191c1204e64559fe8253a0e49e6548", 18),
    # Optimism
    ("optimism", "USDC"): ("0x0b2c639c533813f4aa9d7837caf62653d097ff85", 6),
    ("optimism", "USDT"): ("0x94b008aa00579c1307b0ef2c499ad98a8ce58e58", 6),
    ("optimism", "WETH"): ("0x4200000000000000000000000000000000000006", 18),
    ("optimism", "OP"): ("0x4200000000000000000000000000000000000042", 18),
    # Base
    ("base", "USDC"): ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
    ("base", "USDBC"): ("0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca", 6),
    ("base", "WETH"): ("0x4200000000000000000000000000000000000006", 18),
    # Avalanche
    ("avalanche", "USDC"): ("0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e", 6),
    ("avalanche", "USDT"): ("0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7", 6),
    ("avalanche", "WAVAX"): ("0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7", 18),
    ("avalanche", "WETH"): ("0x49d5c2bdffac6ce2bfdb6640f4f80f226bc10bab", 18),
}


_ADD_LIQUIDITY_SELECTOR = "0xe8e33700"
_APPROVE_SELECTOR = "0x095ea7b3"


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


def _resolve_router(chain: str, protocol: str) -> str | None:
    chain_l = chain.lower()
    proto_l = protocol.lower()
    direct = _V2_ROUTERS.get((chain_l, proto_l))
    if direct:
        return direct
    # Forks share router patterns; try common aliases.
    if proto_l in {"sushi", "sushiswap-v2"}:
        return _V2_ROUTERS.get((chain_l, "sushiswap"))
    if proto_l in {"uniswap", "univ2", "uniswap2"}:
        return _V2_ROUTERS.get((chain_l, "uniswap-v2"))
    if proto_l in {"pancake", "pancakeswap-amm", "pancake-v2"}:
        return _V2_ROUTERS.get((chain_l, "pancakeswap-v2"))
    if proto_l in {"trader-joe", "traderjoe", "trader-joe-v2"}:
        # trader-joe-v2 LB is concentrated; only v1 is V2-style.
        return _V2_ROUTERS.get((chain_l, "trader-joe-v1"))
    return None


def _resolve_token(chain: str, symbol: str) -> tuple[str, int] | None:
    return _TOKENS.get((chain.lower(), symbol.upper()))


@dataclass
class UniswapV2DualTokenAdapter:
    adapter_id: str = "uniswap-v2-dual-token"
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
    actions: frozenset[str] = frozenset({"deposit_lp", "add_liquidity", "provide_liquidity"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain.lower() not in self.chains:
            return CapabilityResult(supported=False, reason=f"V2 adapter does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(supported=False, reason=f"V2 adapter not registered for {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"V2 adapter does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=str(request.amount_in),
            fees={"protocol": "0.30%", "router": "0"},
            metadata={"protocol": request.protocol, "chain": request.chain, "mode": "dual-token"},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"V2 adapter cannot build on chain {request.chain}.")

        router = _resolve_router(chain_norm, request.protocol)
        if router is None:
            raise ValueError(
                f"No V2 router registered for {request.protocol} on {chain_norm}."
            )

        extra = request.extra or {}
        # Dual-token mode requires both legs. The runtime supplies token_a /
        # token_b / amount_a / amount_b in `extra` when the parser captures the
        # "X TOKEN_A and Y TOKEN_B" phrasing. Fall back to asset_in + the pool
        # symbol when only one amount was given (single-sided path is a TODO).
        symbol_a = (extra.get("token_a") or request.asset_in).upper()
        symbol_b = (extra.get("token_b") or "").upper()
        amount_a_raw = extra.get("amount_a") or request.amount_in
        amount_b_raw = extra.get("amount_b")

        pool_symbol = (extra.get("pool_symbol") or "").upper()
        if not symbol_b and pool_symbol:
            parts = [p for p in pool_symbol.replace("/", "-").split("-") if p]
            if len(parts) >= 2:
                # Choose the side that isn't the input.
                cand = parts[1] if parts[0] == symbol_a else parts[0]
                symbol_b = cand
        if not symbol_b:
            raise ValueError(
                "V2 dual-token deposit needs both sides. Pass the pair like "
                "'100 USDC and 0.05 WETH', or include token_b in extra."
            )

        if amount_b_raw is None:
            raise ValueError(
                f"V2 dual-token deposit requires an amount for both legs "
                f"({symbol_a} and {symbol_b}). Re-prompt with both amounts."
            )

        token_a_meta = _resolve_token(chain_norm, symbol_a)
        token_b_meta = _resolve_token(chain_norm, symbol_b)
        if token_a_meta is None:
            raise ValueError(f"No token metadata for {symbol_a} on {chain_norm}.")
        if token_b_meta is None:
            raise ValueError(f"No token metadata for {symbol_b} on {chain_norm}.")
        addr_a, dec_a = token_a_meta
        addr_b, dec_b = token_b_meta

        try:
            amount_a_dec = Decimal(str(amount_a_raw))
            amount_b_dec = Decimal(str(amount_b_raw))
        except Exception as exc:
            raise ValueError(f"Invalid amount: {exc}")
        if amount_a_dec <= 0 or amount_b_dec <= 0:
            raise ValueError("Both amounts must be > 0 for V2 addLiquidity.")

        amount_a_units = _to_unit(amount_a_dec, dec_a)
        amount_b_units = _to_unit(amount_b_dec, dec_b)
        slippage_bps = max(int(request.slippage_bps or 100), 10)
        min_a_units = (amount_a_units * (10_000 - slippage_bps)) // 10_000
        min_b_units = (amount_b_units * (10_000 - slippage_bps)) // 10_000
        deadline = int(time.time()) + 30 * 60  # 30 min

        # addLiquidity calldata.
        add_calldata = (
            _ADD_LIQUIDITY_SELECTOR
            + _encode_address(addr_a)
            + _encode_address(addr_b)
            + _encode_uint256(amount_a_units)
            + _encode_uint256(amount_b_units)
            + _encode_uint256(min_a_units)
            + _encode_uint256(min_b_units)
            + _encode_address(request.user_address)
            + _encode_uint256(deadline)
        )

        approve_a_calldata = (
            _APPROVE_SELECTOR + _encode_address(router) + _encode_uint256(amount_a_units)
        )
        approve_b_calldata = (
            _APPROVE_SELECTOR + _encode_address(router) + _encode_uint256(amount_b_units)
        )

        proto_label = request.protocol.replace("-", " ").title()
        approve_a_step = make_step(
            index=1,
            action="approve",
            title=f"Approve {symbol_a} for {proto_label} router",
            description=(
                f"Approve {amount_a_dec} {symbol_a} so the {proto_label} router"
                f"can pull funds for the addLiquidity call."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=symbol_a,
            amount_in=str(amount_a_dec),
            slippage_bps=0,
            gas_estimate_usd=1.4,
            duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=addr_a,
                data=approve_a_calldata,
                value="0x0",
                spender=router,
            ),
            risk_warnings=[
                f"Approval grants {proto_label} router the exact amount you authorize.",
            ],
        )
        approve_b_step = make_step(
            index=2,
            action="approve",
            title=f"Approve {symbol_b} for {proto_label} router",
            description=(
                f"Approve {amount_b_dec} {symbol_b} so the {proto_label} router"
                f"can pull funds for the addLiquidity call."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=symbol_b,
            amount_in=str(amount_b_dec),
            slippage_bps=0,
            gas_estimate_usd=1.4,
            duration_estimate_s=15,
            depends_on=[approve_a_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=addr_b,
                data=approve_b_calldata,
                value="0x0",
                spender=router,
            ),
            risk_warnings=[
                f"Approval grants {proto_label} router the exact amount you authorize.",
            ],
        )
        add_step = make_step(
            index=3,
            action="add_liquidity",
            title=f"Add liquidity to {proto_label} {symbol_a}/{symbol_b}",
            description=(
                f"Deposit {amount_a_dec} {symbol_a} + {amount_b_dec} {symbol_b} into "
                f"the {proto_label} pool. Slippage cap {slippage_bps / 100:.2f}%. "
                f"You receive an LP token in your wallet."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=f"{symbol_a}+{symbol_b}",
            amount_in=f"{amount_a_dec} {symbol_a} + {amount_b_dec} {symbol_b}",
            asset_out=f"LP-{symbol_a}-{symbol_b}",
            slippage_bps=slippage_bps,
            gas_estimate_usd=4.0,
            duration_estimate_s=20,
            depends_on=[approve_b_step.step_id],
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
        return [approve_a_step, approve_b_step, add_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(
            confirmed=False,
            detail="V2 LP verification requires on-chain LP-token balance read; wired in V2.",
        )
