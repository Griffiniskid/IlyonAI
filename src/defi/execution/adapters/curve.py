"""Curve native single-sided add_liquidity adapter (Phase 6).

Curve stable pools accept asymmetric deposits natively — pass an amounts
array with zeros for the slots you do not want to contribute. No external
swap is required. The pool internally rebalances and mints LP at the cost
of a small slippage.

Selectors:
  add_liquidity(uint256[2],uint256)  -> 0x0b4c7e4d
  add_liquidity(uint256[3],uint256)  -> 0x4515cef3
  add_liquidity(uint256[4],uint256)  -> 0xb72df5de
"""
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


_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
}

# (chain, pool_key) -> {address, coins[(symbol, address, decimals)]}
# Pool keys are lower-cased canonical labels. Resolution accepts: explicit
# pool_address (extra), pool_key match, or "auto" — find the pool whose coin
# set contains asset_in.
_CURVE_POOLS: dict[tuple[str, str], dict] = {
    ("ethereum", "3pool"): {
        "address": "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
        "coins": [
            ("DAI", "0x6b175474e89094c44da98b954eedeac495271d0f", 18),
            ("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
            ("USDT", "0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
        ],
    },
    ("ethereum", "crvusd-usdc"): {
        "address": "0x4dece678ceceb27446b35c672dc7d61f30bad69e",
        "coins": [
            ("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
            ("crvUSD", "0xf939e0a03fb07f59a73314e73794be0e57ac1b4e", 18),
        ],
    },
    ("ethereum", "crvusd-usdt"): {
        "address": "0x390f3595bca2df7d23783dfd126427cceb997bf4",
        "coins": [
            ("USDT", "0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
            ("crvUSD", "0xf939e0a03fb07f59a73314e73794be0e57ac1b4e", 18),
        ],
    },
    # Polygon aave-style 3pool (aDAI/aUSDC/aUSDT) is wrapped and complex; skip.
    ("polygon", "atricrypto3"): {
        "address": "0x445fe580ef8d70ff569ab36e80c647af338db351",
        "coins": [
            ("DAI", "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063", 18),
            ("USDC", "0x2791bca1f2de4661ed88a30c99a7a9449aa84174", 6),
            ("USDT", "0xc2132d05d31c914a87c6611c10748aeb04b58e8f", 6),
        ],
    },
    ("arbitrum", "2pool"): {
        "address": "0x7f90122bf0700f9e7e1f688fe926940e8839f353",
        "coins": [
            ("USDC", "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8", 6),
            ("USDT", "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", 6),
        ],
    },
    ("optimism", "3pool"): {
        "address": "0x1337bedc9d22ecbe766df105c9623922a27963ec",
        "coins": [
            ("DAI", "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", 18),
            ("USDC", "0x7f5c764cbc14f9669b88837ca1490cca17c31607", 6),
            ("USDT", "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58", 6),
        ],
    },
    ("base", "4pool"): {
        "address": "0xf6c5f01c7f3148891ad0e19df78743d31e390d1f",
        "coins": [
            ("USDC", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
            ("crvUSD", "0x417ac0e078398c154eded8f5e0f56b78aa3f04e0", 18),
            ("USDbC", "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca", 6),
        ],
    },
}

_ADD_LIQUIDITY_SELECTORS = {
    2: "0x0b4c7e4d",
    3: "0x4515cef3",
    4: "0xb72df5de",
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
    """Find the Curve pool to use. Returns (pool_key, pool_meta) or None."""
    chain_l = chain.lower()
    asset_u = asset_in.upper()
    if pool_hint:
        ph = pool_hint.lower()
        for (c, k), meta in _CURVE_POOLS.items():
            if c != chain_l:
                continue
            if k == ph or meta["address"].lower() == ph:
                return k, meta
    # Auto: any pool on this chain containing asset_in. Prefer 3pool.
    for (c, k), meta in _CURVE_POOLS.items():
        if c != chain_l:
            continue
        coin_syms = {sym.upper() for sym, _, _ in meta["coins"]}
        if asset_u in coin_syms:
            return k, meta
    return None


@dataclass
class CurveSingleSidedAdapter:
    adapter_id: str = "curve-stable-singlesided"
    chains: frozenset[str] = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base"})
    protocols: frozenset[str] = frozenset({"curve", "curve-dex", "curve-finance", "curve-stable"})
    actions: frozenset[str] = frozenset({"deposit_lp", "add_liquidity", "provide_liquidity"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain.lower() not in self.chains:
            return CapabilityResult(supported=False, reason=f"Curve adapter does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Adapter is for Curve, not {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"Curve adapter does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=str(request.amount_in),
            fees={"protocol": "0.04%", "router": "0"},
            metadata={"protocol": "curve", "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"Curve adapter cannot build on chain {request.chain}.")

        extra = request.extra or {}
        pool_hint = extra.get("pool_key") or extra.get("pool_address") or extra.get("poolAddress")
        resolved = _resolve_pool(chain_norm, pool_hint, request.asset_in)
        if resolved is None:
            raise ValueError(
                f"No Curve pool registered on {chain_norm} containing {request.asset_in}; "
                "pass extra.pool_address or extra.pool_key for non-canonical pools."
            )
        pool_key, pool_meta = resolved
        pool_address = pool_meta["address"]
        coins = pool_meta["coins"]
        n_coins = len(coins)
        selector = _ADD_LIQUIDITY_SELECTORS.get(n_coins)
        if selector is None:
            raise ValueError(f"Curve pool with {n_coins} coins not yet supported (selector missing).")

        # Locate the input coin's slot.
        asset_u = request.asset_in.upper()
        coin_index = None
        token_address = None
        decimals = None
        for idx, (sym, addr, dec) in enumerate(coins):
            if sym.upper() == asset_u:
                coin_index = idx
                token_address = addr
                decimals = dec
                break
        if coin_index is None:
            raise ValueError(
                f"Curve pool {pool_key} on {chain_norm} does not contain {asset_u}; "
                f"coins = {[s for s, _, _ in coins]}."
            )

        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        # min_mint_amount with conservative slippage. Curve LP shares are
        # roughly USD-pegged for stable pools; ratio ≈ 1:1 minus pool fee.
        slippage_bps = max(int(request.slippage_bps or 50), 10)
        # Naive: amount_units * (1 - slip), scaled to 18 decimals where LP lives.
        scale_to_18 = 10 ** (18 - decimals) if decimals < 18 else 1
        scale_down_18 = 10 ** (decimals - 18) if decimals > 18 else 1
        scaled_units = amount_units * scale_to_18 // scale_down_18
        min_mint = (scaled_units * (10_000 - slippage_bps)) // 10_000

        # Build add_liquidity(uint256[N], uint256 min_mint) calldata.
        amount_slots: list[int] = [0] * n_coins
        amount_slots[coin_index] = amount_units
        encoded_amounts = "".join(_encode_uint256(a) for a in amount_slots)
        add_calldata = selector + encoded_amounts + _encode_uint256(min_mint)

        # ERC20 approve(pool, amount).
        approve_calldata = "0x095ea7b3" + _encode_address(pool_address) + _encode_uint256(amount_units)

        approve_step = make_step(
            index=1,
            action="approve",
            title=f"Approve {request.asset_in} for Curve {pool_key}",
            description=(
                f"Approve {request.amount_in} {request.asset_in} so the Curve "
                f"{pool_key} pool can pull funds."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol="curve",
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
                "Approval grants Curve pool the exact amount you authorize.",
            ],
        )

        add_step = make_step(
            index=2,
            action="add_liquidity",
            title=f"Add liquidity to Curve {pool_key}",
            description=(
                f"Single-sided deposit of {request.amount_in} {request.asset_in} "
                f"into Curve {pool_key} ({n_coins}-coin stable pool). Pool rebalances "
                f"internally; expect ≤{slippage_bps / 100:.2f}% drift vs $1 LP value."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol="curve",
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"crv{pool_key.upper()}",
            slippage_bps=slippage_bps,
            gas_estimate_usd=4.0,
            duration_estimate_s=20,
            depends_on=[approve_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=pool_address,
                data=add_calldata,
                value="0x0",
                spender=pool_address,
            ),
            risk_warnings=[
                "Single-sided deposits incur Curve's imbalance fee (≈0.04%).",
                "LP token represents pooled balance — withdraw to base coins later.",
            ],
        )
        return [approve_step, add_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(
            confirmed=False,
            detail="Curve verification requires on-chain LP balance read; wired in V2.",
        )
