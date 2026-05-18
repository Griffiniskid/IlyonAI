"""EVM LST + LRT direct-mint adapter — consumes src/defi/execution/lst_registry.

For each protocol in the registry (Lido / Rocket Pool / ether.fi / Frax /
Mantle / Renzo / Kelp / Swell / Puffer), emit the canonical direct-mint
calldata. Each protocol publishes its own selector + arg shape; this
adapter dispatches by selector and encodes per-shape.

Selector → arg shape:
  0xa1903eab  Lido         submit(address referral) → 1 word
  0xa3e0464d  Rocket Pool  deposit()                → 0 words
  0xd5c08a72  ether.fi     deposit()                → 0 words
  0x4dcd4547  Frax         submit()                 → 0 words
  0xf6326fb3  Mantle       stake()                  → 0 words
  0xfdaf83a3  Renzo        depositETH(referral)     → 1 word
  0xf340fa01  Swell        deposit()                → 0 words
  0xb6b55f25  Puffer       deposit(uint256)         → 1 word (ERC-4626 deposit)
  0x47e7ef24  Kelp         depositAsset(asset, amount) → 2 words (ERC20 path)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    parse_receipt_logs,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.lst_registry import LstEntry, lookup_lst
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step


_APPROVE_SELECTOR = "0x095ea7b3"

# Native ETH-deposit + no extra args → selector alone is full calldata.
_NATIVE_NO_ARGS = frozenset({
    "0xa3e0464d",  # Rocket Pool deposit
    "0xd5c08a72",  # ether.fi deposit
    "0x4dcd4547",  # Frax submit
    "0xf6326fb3",  # Mantle stake
    "0xf340fa01",  # Swell deposit
})

# Native ETH-deposit with a single `referral` address arg.
_NATIVE_REFERRAL = frozenset({
    "0xa1903eab",  # Lido submit(address)
    "0xfdaf83a3",  # Renzo depositETH(address)
})

# Protocols this adapter owns end-to-end.
_PROTOCOLS = frozenset({
    "lido",
    "rocket-pool", "rocketpool", "rocket",
    "ether.fi", "ether-fi", "etherfi",
    "frax-ether", "fraxether", "frax",
    "mantle",
    "renzo",
    "kelp", "kelp-dao",
    "swell",
    "puffer",
})

_ACTIONS = frozenset({
    "supply", "deposit", "lend", "stake", "mint", "deposit_lp", "provide_liquidity",
})


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


_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1, "polygon": 137, "arbitrum": 42161,
    "optimism": 10, "base": 8453,
}


def _resolve_entry(chain: str, asset_in: str, protocol: str) -> LstEntry | None:
    """The user may type either the receipt symbol ('stETH') or the underlying
    asset ('ETH') — for native LSTs the underlying is always the chain's
    native gas, so we look up by the symbol the registry registered."""
    chain_l = chain.lower()
    asset_u = asset_in.upper()
    # 1. Direct symbol match.
    direct = lookup_lst(chain_l, asset_u)
    if direct:
        return direct
    # 2. Protocol-based fallback — pick the registry entry whose protocol
    # name matches the request when the user typed the underlying.
    proto_l = protocol.lower().replace("_", "-")
    # Normalise aliases.
    proto_norm = {
        "rocketpool": "rocket-pool", "rocket": "rocket-pool",
        "etherfi": "ether.fi", "ether-fi": "ether.fi",
        "fraxether": "frax-ether", "frax": "frax-ether",
        "kelp-dao": "kelp",
    }.get(proto_l, proto_l)
    from src.defi.execution.lst_registry import _REGISTRY
    for (c, _sym), entry in _REGISTRY.items():
        if c != chain_l:
            continue
        if entry.protocol == proto_norm:
            return entry
    return None


@dataclass
class EvmLstDirectMintAdapter:
    adapter_id: str = "evm-lst-direct-mint"
    chains: frozenset[str] = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base"})
    protocols: frozenset[str] = _PROTOCOLS
    actions: frozenset[str] = _ACTIONS
    # V7-043 — canonical ERC20 Transfer(address,address,uint256) topic0.
    # LST direct mints emit Transfer(0x0, user, shares) on the receipt token
    # (stETH, rETH, cbETH, etc.) which is the canonical mint-proof.
    EXPECTED_TOPIC0: str = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain.lower() not in self.chains:
            return CapabilityResult(False, None, f"EVM LST adapter does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(False, None, f"EVM LST adapter is not for {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(False, None, f"EVM LST adapter does not handle {action}.")
        return CapabilityResult(True, self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=str(request.amount_in),
            fees={"protocol": "0 (rate-limit / fee depending on LST)"},
            metadata={"protocol": request.protocol, "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"EVM LST adapter cannot build on chain {request.chain}.")

        entry = _resolve_entry(chain_norm, request.asset_in, request.protocol)
        if entry is None:
            raise ValueError(
                f"No LST registry entry for {request.protocol} {request.asset_in} on {chain_norm}."
            )
        mint = entry.direct_mint
        if mint is None:
            raise ValueError(
                f"{entry.protocol} has no direct-mint path on {chain_norm}; use secondary market."
            )

        extra = request.extra or {}
        amount_units = _to_unit(request.amount_in, 18)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        # Honor per-protocol minimum deposit.
        if mint.min_deposit_native > 0:
            min_units = _to_unit(Decimal(str(mint.min_deposit_native)), 18)
            if amount_units < min_units:
                raise ValueError(
                    f"{entry.protocol} requires min deposit of {mint.min_deposit_native} "
                    f"native units; got {request.amount_in}."
                )

        proto_label = entry.protocol.replace("-", " ").title()

        # ── Native ETH paths ──
        if mint.native_eth:
            if mint.selector in _NATIVE_NO_ARGS:
                calldata = mint.selector
            elif mint.selector in _NATIVE_REFERRAL:
                referral = (extra.get("referral") or request.user_address)
                calldata = mint.selector + _encode_address(referral)
            else:
                raise ValueError(
                    f"Unknown native-ETH selector shape {mint.selector} for {entry.protocol}."
                )
            value_hex = "0x" + format(amount_units, "x")
            step = make_step(
                index=1, action="stake",
                title=f"Stake {request.amount_in} ETH via {proto_label}",
                description=(
                    f"Direct mint at {mint.contract} ({mint.selector}). "
                    f"msg.value carries {request.amount_in} ETH. "
                    f"You receive {entry.receipt_token}."
                ),
                chain=request.chain, wallet="MetaMask", protocol=request.protocol,
                asset_in="ETH", amount_in=str(request.amount_in),
                asset_out=entry.receipt_token,
                slippage_bps=0, gas_estimate_usd=2.6, duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=mint.contract, data=calldata, value=value_hex,
                    spender=mint.contract,
                ),
                risk_warnings=[
                    f"{proto_label} {entry.receipt_token} accrues yield via rebase or share-price.",
                    mint.note or f"Receipt token {entry.receipt_token}.",
                ],
            )
            return [step]

        # ── ERC20-in paths (Kelp depositAsset / Puffer ERC-4626) ──
        # Auto-wrap path: when user passes asset_in=ETH but the protocol
        # requires ERC20 input, default to WETH on the same chain + prepend
        # a wrap step (WETH.deposit() selector 0xd0e30db0). Caught by v4-A18
        # blocking on Kelp ETH input.
        _WETH_ADDRS: dict[str, str] = {
            "ethereum": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            "arbitrum": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
            "optimism": "0x4200000000000000000000000000000000000006",
            "base":     "0x4200000000000000000000000000000000000006",
            "polygon":  "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619",
            "avalanche": "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7",
        }
        chain_norm = request.chain.lower()
        token_in_address = extra.get("token_address")
        _auto_wrap = False
        if not token_in_address:
            if request.asset_in.upper() == "ETH" and chain_norm in _WETH_ADDRS:
                token_in_address = _WETH_ADDRS[chain_norm]
                _auto_wrap = True
            else:
                raise ValueError(
                    f"{entry.protocol} mint expects ERC20 input — pass extra.token_address."
                )
        if mint.selector == "0x47e7ef24":  # Kelp depositAsset(address, uint256)
            calldata = (
                mint.selector
                + _encode_address(token_in_address)
                + _encode_uint256(amount_units)
            )
        elif mint.selector == "0xb6b55f25":  # Puffer deposit(uint256) — ERC-4626
            calldata = mint.selector + _encode_uint256(amount_units)
        else:
            raise ValueError(f"Unknown ERC20 selector shape {mint.selector}")

        # Wrap step first when auto-wrap fired
        wrap_step = None
        if _auto_wrap:
            wrap_step = make_step(
                index=1, action="approve",  # 'wrap' not in canonical actions enum yet
                title=f"Wrap {request.amount_in} ETH → WETH",
                description=(
                    f"WETH.deposit() at {token_in_address}. msg.value carries {request.amount_in} ETH. "
                    f"Required because {proto_label} mint accepts ERC20 input."
                ),
                chain=request.chain, wallet="MetaMask", protocol=request.protocol,
                asset_in="ETH", amount_in=str(request.amount_in),
                asset_out="WETH",
                slippage_bps=0, gas_estimate_usd=1.4, duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=token_in_address, data="0xd0e30db0", value="0x" + format(amount_units, "x"),
                    spender=token_in_address,
                ),
                risk_warnings=["Wrap converts native ETH to WETH 1:1; unwrap is symmetric."],
            )

        approve_calldata = (
            _APPROVE_SELECTOR + _encode_address(mint.contract) + _encode_uint256(amount_units)
        )
        approve_step = make_step(
            index=2 if wrap_step else 1, action="approve",
            title=f"Approve {'WETH' if _auto_wrap else request.asset_in} for {proto_label}",
            description=(
                f"Approve {request.amount_in} {request.asset_in} so {proto_label} "
                f"can pull funds for direct mint."
            ),
            chain=request.chain, wallet="MetaMask", protocol=request.protocol,
            asset_in=request.asset_in, amount_in=str(request.amount_in),
            slippage_bps=0, gas_estimate_usd=1.4, duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm", chain_id=chain_id,
                to=token_in_address, data=approve_calldata, value="0x0",
                spender=mint.contract,
            ),
        )
        mint_step = make_step(
            index=3 if wrap_step else 2, action="stake",
            title=f"Mint {entry.receipt_token} via {proto_label}",
            description=(
                f"Direct mint at {mint.contract} ({mint.selector}). "
                f"You receive {entry.receipt_token}."
            ),
            chain=request.chain, wallet="MetaMask", protocol=request.protocol,
            asset_in=request.asset_in, amount_in=str(request.amount_in),
            asset_out=entry.receipt_token,
            slippage_bps=0, gas_estimate_usd=3.0, duration_estimate_s=15,
            depends_on=[approve_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm", chain_id=chain_id,
                to=mint.contract, data=calldata, value="0x0",
                spender=mint.contract,
            ),
            risk_warnings=[
                f"{proto_label} direct mint may queue when daily cap is hit.",
            ],
        )
        if wrap_step:
            return [wrap_step, approve_step, mint_step]
        return [approve_step, mint_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        """Parse receipt logs for canonical ERC20 Transfer mint topic0.

        LST direct mints (Lido submit, Rocket deposit, Frax submit, etc.) emit
        an ERC20 Transfer from the zero address to the user on the receipt
        token. We confirm by topic0 presence; mint-quantity attribution is
        decoded from log.data by the position-tracker.
        """
        receipt = request.receipt or (request.expected_position or {}).get("receipt")
        return parse_receipt_logs(receipt, self.EXPECTED_TOPIC0)
