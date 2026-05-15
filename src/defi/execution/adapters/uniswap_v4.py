"""Uniswap V4 native mint adapter — spec §6a.

PoolKey resolution + V4 PositionManager.modifyLiquidities for mint.

Action codes (per @uniswap/v4-periphery):
  MINT_POSITION       = 0x02
  SETTLE_PAIR         = 0x0d
  TAKE_PAIR           = 0x0e

Plan shape:
  1. Optional Enso swap input → USDC (when input not already in pool legs)
  2. ERC20.approve USDC → Permit2 (one-time max)
  3. Permit2.approve(USDC, PositionManager, deposit×1.05, expiration)
  4. PositionManager.modifyLiquidities(unlockData, deadline) [msg.value = ETH leg]

Hook allowlist enforced via src.shield.v4_hook_allowlist — unknown hooks refuse.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from src.data.asset_registry import NATIVE_PLACEHOLDER, resolve_any_evm_token
from src.data.v3_tick_math import (
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
from src.shield.v4_hook_allowlist import is_allowed as hook_is_allowed
from src.shield.v4_hook_allowlist import shield_verdict_for_hook

_APPROVE_SEL = "0x095ea7b3"
_MODIFY_LIQ_SEL = "0xdd46508f"  # modifyLiquidities(bytes,uint256)
_PERMIT2_APPROVE_SEL = "0x87517c45"  # Permit2.approve(token,spender,amount,expiration)

_ACTION_MINT_POSITION = 0x02
_ACTION_SETTLE_PAIR = 0x0d
_ACTION_TAKE_PAIR = 0x0e

# Permit2 canonical address — same on every EVM chain.
_PERMIT2 = "0x000000000022d473030f116ddee9f6b43ac78ba3"

# V4 PoolManager + PositionManager per chain (canonical deploys 2024-2025).
_V4_POOL_MANAGER: dict[str, str] = {
    "ethereum": "0x000000000004444c5dc75cB358380D2e3dE08A90",
    "base":     "0x498581fF718922c3f8e6A244956aF099B2652b2b",
    "arbitrum": "0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32",
    "optimism": "0x9a13F98Cb987694C9F086b1F5eB990EeA8264Ec3",
    "polygon":  "0x67366782805870060151383F4BbFF9daB53e5cD6",
    "bsc":      "0x28e2Ea090877bF75740558f6BFB36A5ffeE9e9dF",
    "avalanche":"0x06380C0e0912312B5150364B9DC4542BA0DbBc85",
    "unichain": "0x1F98400000000000000000000000000000000004",
}
_V4_POSITION_MANAGER: dict[str, str] = {
    "ethereum": "0xbD216513d74C8cf14cf4747E6AaA6420FF64ee9e",
    "base":     "0x7C5f5A4bBd8fD63184577525326123B519429bDc",
    "arbitrum": "0xd88F38F930b7952f2DB2432Cb002E7abbF3dD869",
    "optimism": "0x3C3Ea4B57a46241e54610e5f022E5c45859A1017",
    "polygon":  "0x1Ec2eBF4F37E7363FDfe3551602425af0B3ceef9",
    "bsc":      "0x7A4a5c919aE2541AeD11041A1AEeE68f1287f95b",
    "avalanche":"0xB74b1F14d2754AcfcbBe1a221023a5cf50Ab8ACD",
    "unichain": "0x4529A01c7A0410167c5740C487A8DE60232617bf",
}

_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,  "polygon": 137, "arbitrum": 42161, "optimism": 10,
    "base": 8453,   "avalanche": 43114, "bsc": 56, "unichain": 130,
}


def _pad32(hex_str: str) -> str:
    return hex_str.lower().removeprefix("0x").rjust(64, "0")


def _enc_addr(addr: str) -> str:
    return _pad32(addr)


def _enc_uint(v: int) -> str:
    if v < 0:
        v = v & ((1 << 256) - 1)
    return format(v, "064x")


def _enc_int24(v: int) -> str:
    return _enc_uint(v)


def _to_units(amount: Decimal, decimals: int) -> int:
    return int(amount * (Decimal(10) ** decimals))


def _encode_pool_key(currency0: str, currency1: str, fee: int, tick_spacing: int, hooks: str) -> str:
    """PoolKey struct: (address currency0, address currency1, uint24 fee,
    int24 tickSpacing, address hooks). 5 × 32 = 160 bytes."""
    return (
        _enc_addr(currency0)
        + _enc_addr(currency1)
        + _enc_uint(fee)
        + _enc_int24(tick_spacing)
        + _enc_addr(hooks)
    )


def _encode_mint_position_params(
    *,
    currency0: str, currency1: str, fee: int, tick_spacing: int, hooks: str,
    tick_lower: int, tick_upper: int, liquidity: int,
    amount0_max: int, amount1_max: int, owner: str, hook_data: bytes = b"",
) -> str:
    """MINT_POSITION params (dynamic abi.encode):
    (PoolKey, int24, int24, uint256, uint128, uint128, address, bytes)."""
    # Dynamic encoding: 8 head slots first, then tail.
    # All fields except `bytes hookData` are static; PoolKey is inlined.
    pool_key_hex = _encode_pool_key(currency0, currency1, fee, tick_spacing, hooks)
    head = (
        pool_key_hex                              # 160 bytes inlined for the inner struct
        + _enc_int24(tick_lower)
        + _enc_int24(tick_upper)
        + _enc_uint(liquidity)
        + _enc_uint(amount0_max)
        + _enc_uint(amount1_max)
        + _enc_addr(owner)
        # hookData offset placeholder — points to tail right after this head.
        # Head width: 160 (PoolKey) + 32*6 + 32 (hookData offset) = 384 bytes.
        + _enc_uint(384)
    )
    hd = hook_data or b""
    tail = _enc_uint(len(hd)) + (hd.hex().ljust(((len(hd) + 31) // 32) * 64, "0") if hd else "")
    return head + tail


def _encode_settle_pair_params(currency0: str, currency1: str) -> str:
    """SETTLE_PAIR params: (Currency, Currency)."""
    return _enc_addr(currency0) + _enc_addr(currency1)


def _encode_take_pair_params(currency0: str, currency1: str, recipient: str) -> str:
    """TAKE_PAIR params: (Currency, Currency, address)."""
    return _enc_addr(currency0) + _enc_addr(currency1) + _enc_addr(recipient)


def _encode_actions(action_codes: list[int]) -> bytes:
    """abi.encodePacked actions — single byte each."""
    return bytes(action_codes)


def _encode_unlock_data(actions: bytes, param_hex_list: list[str]) -> str:
    """abi.encode(bytes actions, bytes[] params).

    Both `actions` and each entry in `params` are dynamic `bytes`. Two-level
    dynamic encoding: head slots point to tails.
    """
    # Head:
    # offset to actions (32), offset to params array (32)
    actions_offset = 64  # right after the two head slots
    actions_len = len(actions)
    actions_padded = actions.hex().ljust(((actions_len + 31) // 32) * 64, "0")
    actions_block = _enc_uint(actions_len) + actions_padded
    actions_block_bytes = 32 + ((actions_len + 31) // 32) * 32

    params_offset = actions_offset + actions_block_bytes

    # params array: length, then offsets[], then each param block.
    n = len(param_hex_list)
    param_lengths_bytes = []
    param_padded = []
    for p_hex in param_hex_list:
        b = bytes.fromhex(p_hex)
        param_lengths_bytes.append(len(b))
        param_padded.append(p_hex.ljust(((len(b) + 31) // 32) * 64, "0"))

    # offsets table (relative to start of array payload, after the length slot)
    offsets_hex = []
    cursor = 32 * n  # after the offsets table
    for i in range(n):
        offsets_hex.append(_enc_uint(cursor))
        cursor += 32 + ((param_lengths_bytes[i] + 31) // 32) * 32

    params_block = _enc_uint(n) + "".join(offsets_hex)
    for i in range(n):
        params_block += _enc_uint(param_lengths_bytes[i]) + param_padded[i]

    return _enc_uint(actions_offset) + _enc_uint(params_offset) + actions_block + params_block


class UniswapV4NativeAdapter:
    adapter_id = "uniswap-v4"
    chains = {"ethereum", "polygon", "arbitrum", "optimism", "base", "bsc", "avalanche", "unichain"}
    protocols = {"uniswap-v4"}
    actions = {"deposit_lp"}

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain not in self.chains:
            return CapabilityResult(False, None, f"V4 not deployed on {chain}.")
        if protocol not in self.protocols:
            return CapabilityResult(False, None, f"Adapter does not handle {protocol}.")
        if action not in self.actions:
            return CapabilityResult(False, None, f"V4 adapter only handles deposit_lp; saw {action}.")
        return CapabilityResult(True, self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={},
            metadata={"protocol": "uniswap-v4"},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain = request.chain
        chain_id = _CHAIN_IDS[chain]
        pm = _V4_POSITION_MANAGER[chain]
        extra = request.extra or {}
        pool_symbol = (extra.get("pool_symbol") or "").upper()
        fee_bps = int(extra.get("fee_bps") or 500)
        tick_spacing = int(extra.get("tick_spacing") or self._tick_spacing_for_fee(fee_bps))
        hooks_addr = (extra.get("hooks") or "0x" + "00" * 20).lower()
        allow_experimental = bool(extra.get("allow_experimental_hook") or False)

        if not hook_is_allowed(hooks_addr, chain_id, allow_experimental=allow_experimental):
            verdict = shield_verdict_for_hook(hooks_addr, chain_id)
            raise ValueError(
                f"V4 hook refused by Shield: {verdict.get('headline')}. {verdict.get('detail')}"
            )

        # Parse pair "ETH-USDC" → token0/1 with V4 currency ordering (lower address first).
        if "-" not in pool_symbol:
            raise ValueError("V4 build requires extra.pool_symbol like 'ETH-USDC'.")
        sym_a, sym_b = pool_symbol.split("-", 1)
        # Native gas-token symbol per chain — V4 currency for native is address(0).
        native_sym = {
            "ethereum": "ETH", "arbitrum": "ETH", "optimism": "ETH",
            "base": "ETH", "unichain": "ETH",
            "polygon": "MATIC", "bsc": "BNB", "avalanche": "AVAX",
        }.get(chain, "ETH")
        is_native_a = sym_a == native_sym
        is_native_b = sym_b == native_sym
        if is_native_a:
            addr_a, dec_a = "0x" + "00" * 20, 18
        else:
            r_a = await resolve_any_evm_token(chain, sym_a)
            if not r_a:
                raise ValueError(f"Unknown token {sym_a} on {chain}.")
            addr_a, dec_a = r_a
        if is_native_b:
            addr_b, dec_b = "0x" + "00" * 20, 18
        else:
            r_b = await resolve_any_evm_token(chain, sym_b)
            if not r_b:
                raise ValueError(f"Unknown token {sym_b} on {chain}.")
            addr_b, dec_b = r_b
        # V4 PoolKey requires currency0 < currency1 (numeric address comparison).
        if int(addr_a, 16) > int(addr_b, 16):
            currency0, currency1 = addr_b, addr_a
            dec0, dec1, sym0, sym1 = dec_b, dec_a, sym_b, sym_a
        else:
            currency0, currency1 = addr_a, addr_b
            dec0, dec1, sym0, sym1 = dec_a, dec_b, sym_a, sym_b

        # Range
        lower_pct = float(extra.get("range_lower_pct") or -10.0)
        upper_pct = float(extra.get("range_upper_pct") or 10.0)
        # PoolKey resolver: stub — current spot from cached pool state would
        # require PoolManager.getSlot0(poolId) RPC. For first-cut we hardcode
        # the centered range; downstream Preview reads on-chain slot0 to draw
        # the actual range card.
        current_tick = int(extra.get("current_tick") or 0)
        tick_lower, tick_upper = tick_range_from_pct(
            current_tick=current_tick,
            lower_pct=lower_pct,
            upper_pct=upper_pct,
            tick_spacing=tick_spacing,
        )

        # Amount split (50/50 in dollar value for balanced range — defer
        # ratio_from_range math to V3 helper).
        deposit_units = _to_units(request.amount_in, dec_a)
        half = deposit_units // 2
        # For V4 mint, the user provides amount0Max + amount1Max as upper bounds.
        # Liquidity is computed off the desired ratio; we pass the half-split.
        amount0_max = half
        amount1_max = half
        liquidity = 0  # placeholder — let positionManager compute via amount caps

        owner = request.user_address
        actions = _encode_actions([
            _ACTION_MINT_POSITION,
            _ACTION_SETTLE_PAIR,
            _ACTION_TAKE_PAIR,
        ])
        mint_params = _encode_mint_position_params(
            currency0=currency0, currency1=currency1,
            fee=fee_bps, tick_spacing=tick_spacing, hooks=hooks_addr,
            tick_lower=tick_lower, tick_upper=tick_upper,
            liquidity=liquidity, amount0_max=amount0_max, amount1_max=amount1_max,
            owner=owner,
        )
        settle_params = _encode_settle_pair_params(currency0, currency1)
        take_params = _encode_take_pair_params(currency0, currency1, owner)
        unlock_data = _encode_unlock_data(actions, [mint_params, settle_params, take_params])

        deadline = int(time.time()) + 30 * 60
        # modifyLiquidities(bytes unlockData, uint256 deadline)
        unlock_data_bytes = bytes.fromhex(unlock_data)
        # ABI encode call: selector + (bytes, uint256) head + tail
        head = _enc_uint(64) + _enc_uint(deadline)  # offset 64, then deadline
        tail = _enc_uint(len(unlock_data_bytes)) + unlock_data
        calldata = _MODIFY_LIQ_SEL + head + tail

        msg_value = 0
        if is_native_a or is_native_b:
            # Whichever side maps to address(0) is the native leg.
            native_amount = amount0_max if currency0 == "0x" + "00" * 20 else amount1_max
            msg_value = native_amount

        steps: list[ExecutionStepV3] = []

        # Step A: scoped Permit2.approve for the non-native side, if any.
        non_native_side = None
        if currency0 != "0x" + "00" * 20:
            non_native_side = (currency0, amount0_max, sym0)
        elif currency1 != "0x" + "00" * 20:
            non_native_side = (currency1, amount1_max, sym1)
        step_idx = 1
        if non_native_side and non_native_side[0] != "0x" + "00" * 20:
            tok_addr, max_amt, sym = non_native_side
            # Step A1: ERC20.approve token → Permit2 (max, one-time).
            erc20_approve_calldata = _APPROVE_SEL + _enc_addr(_PERMIT2) + _enc_uint(2**256 - 1)
            steps.append(make_step(
                index=step_idx, action="approve",
                title=f"Approve {sym} to Permit2",
                description=(
                    f"One-time max ERC20 approval so the Permit2 router can pull {sym} for V4 "
                    "mints. Subsequent V4 mints will reuse this approval without another popup."
                ),
                chain=chain, wallet="MetaMask", protocol="uniswap-v4",
                asset_in=sym, amount_in=str(2**256 - 1),
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=tok_addr, data=erc20_approve_calldata, value="0x0", spender=_PERMIT2,
                ),
                gas_estimate_usd=1.5, duration_estimate_s=15,
            ))
            step_idx += 1
            # Step A2: Permit2.approve(token, PositionManager, amount, expiration).
            expiration = deadline
            permit2_calldata = (
                _PERMIT2_APPROVE_SEL
                + _enc_addr(tok_addr)
                + _enc_addr(pm)
                + _enc_uint(int(max_amt * 105 // 100))  # +5% buffer
                + _enc_uint(expiration)
            )
            steps.append(make_step(
                index=step_idx, action="approve",
                title=f"Permit2 → V4 PositionManager",
                description=(
                    f"Scoped Permit2 approval for {sym} → V4 PositionManager — limits the "
                    f"pull to {int(max_amt * 105 // 100)} units with expiry at "
                    f"{expiration}. Mandatory for V4 mints."
                ),
                chain=chain, wallet="MetaMask", protocol="uniswap-v4",
                asset_in=sym, amount_in=str(int(max_amt * 105 // 100)),
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=_PERMIT2, data=permit2_calldata, value="0x0", spender=pm,
                ),
                gas_estimate_usd=2.0, duration_estimate_s=15,
            ))
            step_idx += 1

        # Step B: modifyLiquidities (the actual mint).
        funding_sym = sym_a if is_native_a or sym_a == request.asset_in else sym_b
        steps.append(make_step(
            index=step_idx, action="deposit_lp",
            title=f"Open V4 position [{lower_pct:+.0f}% / {upper_pct:+.0f}%]",
            description=(
                f"V4 mint in {currency0[:6]}…/{currency1[:6]}… {fee_bps/100:.2f}% fee tier · "
                f"tickSpacing {tick_spacing} · hooks {hooks_addr[:8]}…{hooks_addr[-4:]} · "
                f"range ticks {tick_lower}…{tick_upper} · amounts0={amount0_max} amounts1={amount1_max} · "
                f"deadline={deadline}. " + ("Native ETH leg via msg.value." if msg_value else "")
            ),
            chain=chain, wallet="MetaMask", protocol="uniswap-v4",
            asset_in=funding_sym, amount_in=str(request.amount_in),
            asset_out="uniswap-v4-position-nft",
            transaction=UnsignedStepTransaction(
                chain_kind="evm", chain_id=chain_id,
                to=pm, data=calldata, value=hex(msg_value), spender=pm,
            ),
            gas_estimate_usd=8.0, duration_estimate_s=30,
            risk_warnings=[
                f"V4 position NFT minted to {owner}. tokenId from PositionManager Transfer log.",
                f"Range covers ticks {tick_lower}…{tick_upper}; goes out-of-range if "
                f"{sym0}/{sym1} price exits the band.",
                f"Hook contract {hooks_addr} — Shield: "
                f"{shield_verdict_for_hook(hooks_addr, chain_id).get('headline')}",
            ],
        ))
        return steps

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        # V4 receipt verification: PoolManager.Initialize lookup + PositionManager
        # ERC721 Transfer log. Per-kind RPC reader lands in §6g Phase R14.
        return VerifyResult(
            confirmed=False,
            detail="V4 receipt verify: read PositionManager.Transfer for tokenId, then PoolManager.getPositionInfo.",
        )

    def _tick_spacing_for_fee(self, fee_bps: int) -> int:
        # Mirrors V3 defaults; V4 hook pools can override via custom tickSpacing.
        return {100: 1, 500: 10, 3000: 60, 10000: 200}.get(fee_bps, 60)
