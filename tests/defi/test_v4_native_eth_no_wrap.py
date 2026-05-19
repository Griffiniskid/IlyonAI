"""Pin test for V4 native-ETH "do not wrap" guard.

V4 PoolManager accepts native ETH via flash accounting (msg.value, currency
address(0)). Pre-wrapping ETH -> WETH burns gas and produces a currency
the V4 PoolKey doesn't reference. The mint either reverts (PoolKey mismatch)
or strands the WETH in the wallet.

This pin enforces two things:
  1. The V4 build path for asset_in=ETH MUST NOT emit any WETH9.deposit()
     selector (0xd0e30db0) in step calldata.
  2. The V3 NFT build path for asset_in=ETH is still flagged for wrap by
     is_native_wrap_required(...) — V3 pools trade WETH, not native ETH.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.uniswap_v4 import (
    UniswapV4NativeAdapter,
    is_v4_native_lp_no_wrap,
)
from src.defi.execution.composed_plan import (
    WETH9_DEPOSIT_SELECTOR,
    is_native_wrap_required,
)


_WETH9_DEPOSIT_SEL = WETH9_DEPOSIT_SELECTOR  # 0xd0e30db0


def _build_v4_eth_plan():
    """Build a V4 ETH-USDC plan on ethereum with native ETH as funding."""
    adapter = UniswapV4NativeAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="uniswap-v4",
        asset_in="ETH",
        amount_in=Decimal("0.5"),
        user_address="0x000000000000000000000000000000000000dEaD",
        extra={
            "pool_symbol": "ETH-USDC",
            "fee_bps": 500,
            "tick_spacing": 10,
            "hooks": "0x" + "00" * 20,
            "current_tick": 0,
            "usd_equivalent": 1000.0,
            "range_lower_pct": -10.0,
            "range_upper_pct": 10.0,
        },
    )
    return asyncio.run(adapter.build(req))


def test_v4_native_eth_plan_emits_no_weth9_deposit_step():
    """No step in a V4 native-ETH LP plan may carry the WETH9.deposit()
    selector. PoolManager accepts ETH via msg.value directly."""
    steps = _build_v4_eth_plan()
    assert steps, "V4 build returned an empty plan."
    for step in steps:
        data = (getattr(step.transaction, "data", "") or "").lower()
        assert not data.startswith(_WETH9_DEPOSIT_SEL), (
            f"V4 plan emitted a WETH9.deposit() wrap step "
            f"(selector={_WETH9_DEPOSIT_SEL}). Step title={step.title!r}. "
            f"V4 takes native ETH via msg.value — wrapping is wrong and "
            f"burns gas."
        )


def test_v4_native_eth_plan_carries_msg_value_on_mint():
    """The actual V4 mint step must carry msg.value > 0 — that's how the
    native leg gets into PoolManager without a wrap intermediary."""
    steps = _build_v4_eth_plan()
    mint_steps = [s for s in steps if s.action == "deposit_lp"]
    assert mint_steps, "V4 plan missing the modifyLiquidities mint step."
    mint = mint_steps[0]
    value_hex = (getattr(mint.transaction, "value", "0x0") or "0x0").lower()
    value_int = int(value_hex, 16) if value_hex.startswith("0x") else int(value_hex)
    assert value_int > 0, (
        f"V4 mint step carries msg.value={value_hex} — native ETH funding "
        f"must travel via msg.value, not a wrap step."
    )


def test_is_v4_native_lp_no_wrap_predicate_signals_skip_for_eth():
    """The predicate consumed by build_yield_execution_plan must return True
    for (uniswap-v4, ETH) so the wrap-prepend is skipped."""
    assert is_v4_native_lp_no_wrap(protocol="uniswap-v4", asset_in="ETH")
    assert is_v4_native_lp_no_wrap(protocol="uniswap-v4", asset_in="eth")
    # Other native gas tokens on V4 chains also accepted via msg.value.
    assert is_v4_native_lp_no_wrap(protocol="uniswap-v4", asset_in="MATIC")


def test_is_v4_native_lp_no_wrap_predicate_off_for_non_v4():
    """V3 (and every other protocol) must NOT short-circuit the wrap
    prepend — those pools genuinely need WETH."""
    assert not is_v4_native_lp_no_wrap(protocol="uniswap-v3", asset_in="ETH")
    assert not is_v4_native_lp_no_wrap(protocol="pancakeswap-v3", asset_in="ETH")
    # ERC-20 input on V4 (e.g. USDC) doesn't need the guard either.
    assert not is_v4_native_lp_no_wrap(protocol="uniswap-v4", asset_in="USDC")


def test_v3_native_eth_lp_still_flagged_for_wrap():
    """V3 pools trade wrapped natives — is_native_wrap_required must still
    fire for asset_in=ETH so the existing wrap-prepend runs.

    This is the contrapositive of the V4 guard: the plan-builder's wrap
    gate is shared, so we pin V3 to confirm we didn't break the legitimate
    case by adding the V4 short-circuit.
    """
    # The V3 NFT plan-builder action is `deposit_lp`; spec §13 row 3 lists
    # this as the canonical wrap-required verb on mainnet.
    assert is_native_wrap_required(
        chain="ethereum", asset_in="ETH", action="deposit_lp",
    )
    assert is_native_wrap_required(
        chain="ethereum", asset_in="ETH", action="provide_liquidity",
    )
    # And the V4 guard predicate must NOT claim V3 is exempt.
    assert not is_v4_native_lp_no_wrap(protocol="uniswap-v3", asset_in="ETH")
