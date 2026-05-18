"""V7-056 — UniswapV2ZapAdapter single-sided zap pin-test.

Covers the two zap entry points and the canonical V2 router selectors:

  swapExactETHForTokens             0x7ff36ab5
  swapExactTokensForTokens          0x38ed1739
  addLiquidityETH                   0xf305d719
  addLiquidity                      0xe8e33700

The adapter splits the single input 50/50, swaps half through the router,
then calls addLiquidity[ETH] with the remaining input + acquired token.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.uniswap_v2_zap import (
    UniswapV2ZapAdapter,
    _ADD_LIQUIDITY,
    _ADD_LIQUIDITY_ETH,
    _SWAP_EXACT_ETH_FOR_TOKENS,
    _SWAP_EXACT_TOKENS_FOR_TOKENS,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------- #
# zap_in_eth — 1 ETH single-sided into WETH/USDC.                        #
# ---------------------------------------------------------------------- #
def test_zap_in_eth_emits_two_legs_swap_then_addLiquidityETH():
    a = UniswapV2ZapAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="uniswap-v2",
        asset_in="ETH",
        amount_in=Decimal("1"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "zap_in_eth", "token_b": "USDC"},
    )
    steps = _run(a.build(req))

    # Native ETH zap: 2 steps (no approve — value attached).
    assert len(steps) == 2, f"expected 2-step ETH zap, got {len(steps)}"

    swap, add = steps
    # --- Leg 1: swapExactETHForTokens(0.5 ETH → USDC) ---
    assert swap.action == "swap"
    assert swap.transaction.data.startswith(_SWAP_EXACT_ETH_FOR_TOKENS)
    # value attached must equal half (0.5 ETH = 5e17 wei).
    assert int(swap.transaction.value, 16) == 5 * 10**17

    # --- Leg 2: addLiquidityETH(USDC, …) with msg.value = 0.5 ETH ---
    assert add.action == "deposit_lp"
    assert add.transaction.data.startswith(_ADD_LIQUIDITY_ETH)
    assert int(add.transaction.value, 16) == 5 * 10**17
    # add leg waits on the swap leg.
    assert add.depends_on == [swap.step_id]


def test_zap_in_eth_split_is_50_50_by_default():
    a = UniswapV2ZapAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="uniswap-v2", asset_in="ETH",
        amount_in=Decimal("2"),  # 2 ETH → 1+1
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "zap_in_eth", "token_b": "USDC"},
    )
    swap, add = _run(a.build(req))
    one_eth_wei = 10**18
    assert int(swap.transaction.value, 16) == one_eth_wei
    assert int(add.transaction.value, 16) == one_eth_wei


# ---------------------------------------------------------------------- #
# zap_in_token — 1000 USDC single-sided into USDC/WETH.                  #
# ---------------------------------------------------------------------- #
def test_zap_in_token_emits_approve_swap_addLiquidity():
    a = UniswapV2ZapAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="uniswap-v2",
        asset_in="USDC",
        amount_in=Decimal("1000"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "zap_in_token", "token_b": "WETH"},
    )
    steps = _run(a.build(req))

    # ERC-20 zap: approve + swap + addLiquidity = 3 steps.
    assert len(steps) == 3, f"expected approve+swap+add (3 steps), got {len(steps)}"
    approve, swap, add = steps

    assert approve.action == "approve"
    # Approve selector is the standard ERC-20 approve(address,uint256).
    assert approve.transaction.data.startswith("0x095ea7b3")

    # --- Leg 1: swapExactTokensForTokens(500 USDC → WETH) ---
    assert swap.action == "swap"
    assert swap.transaction.data.startswith(_SWAP_EXACT_TOKENS_FOR_TOKENS)
    # No native value on the swap (ERC-20 path).
    assert swap.transaction.value == "0x0"
    # The encoded amountIn (first uint256 after selector) is half of total in
    # token units. USDC has 6 decimals → 500 * 10**6 = 500_000_000.
    selector = _SWAP_EXACT_TOKENS_FOR_TOKENS
    payload = swap.transaction.data[len(selector):]
    amount_in_units = int(payload[:64], 16)
    assert amount_in_units == 500 * 10**6

    # --- Leg 2: addLiquidity(USDC, WETH, 500e6, …) ---
    assert add.action == "deposit_lp"
    assert add.transaction.data.startswith(_ADD_LIQUIDITY)
    assert add.transaction.value == "0x0"
    # depends_on chain: approve <- swap <- add.
    assert swap.depends_on == [approve.step_id]
    assert add.depends_on == [swap.step_id]


def test_zap_in_token_split_is_50_50_by_default():
    a = UniswapV2ZapAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="uniswap-v2", asset_in="USDC",
        amount_in=Decimal("1000"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "zap_in_token", "token_b": "WETH"},
    )
    _approve, swap, add = _run(a.build(req))
    # Swap leg encodes 500 USDC; addLiquidity encodes the remaining 500 USDC
    # as amountADesired (3rd uint256 after the 2 address words).
    swap_payload = swap.transaction.data[len(_SWAP_EXACT_TOKENS_FOR_TOKENS):]
    add_payload = add.transaction.data[len(_ADD_LIQUIDITY):]
    assert int(swap_payload[:64], 16) == 500 * 10**6
    # addLiquidity word layout: tokenA(32) tokenB(32) amountADesired(32) …
    add_a_desired = int(add_payload[64 * 2 : 64 * 3], 16)
    assert add_a_desired == 500 * 10**6


# ---------------------------------------------------------------------- #
# Static surface checks.                                                 #
# ---------------------------------------------------------------------- #
def test_adapter_actions_cover_three_zap_entry_points():
    a = UniswapV2ZapAdapter()
    assert a.actions == frozenset({"zap_in", "zap_in_eth", "zap_in_token"})
    assert len(a.actions) == 3


def test_canonical_selectors_pinned():
    # These selectors are derived from the V2 router function signatures and
    # must NEVER change — calldata interop with deployed routers depends on
    # bit-exact match. If you're tempted to edit, you're probably looking at
    # the wrong selector — re-verify with web3.keccak first.
    assert _SWAP_EXACT_ETH_FOR_TOKENS == "0x7ff36ab5"
    assert _SWAP_EXACT_TOKENS_FOR_TOKENS == "0x38ed1739"
    assert _ADD_LIQUIDITY_ETH == "0xf305d719"
    assert _ADD_LIQUIDITY == "0xe8e33700"


def test_supports_returns_capable_for_eth_zap_on_uniswap_v2():
    a = UniswapV2ZapAdapter()
    cap = a.supports(chain="ethereum", protocol="uniswap-v2", action="zap_in_eth")
    assert cap.supported is True
    assert cap.adapter_id == "uniswap-v2-zap"


def test_supports_rejects_unknown_action():
    a = UniswapV2ZapAdapter()
    cap = a.supports(chain="ethereum", protocol="uniswap-v2", action="bridge")
    assert cap.supported is False
