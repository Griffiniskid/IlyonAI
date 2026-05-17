"""Pin tests for the typed LP intent envelope (spec §3, V7-011..014).

These tests guarantee the enum membership, default values, serialization
roundtrip, and native↔wrapped alias mapping. Anything that changes the
public shape of :mod:`src.agent.intent.liquidity_intent` must update
these pins.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agent.intent.liquidity_intent import (
    NATIVE_FROM_WRAPPED,
    RANGE_PRESET_BPS,
    WETH_NATIVE_ALIAS_MAP,
    AmountMode,
    LiquidityIntent,
    LpAction,
    LpStrategy,
    RangePreset,
)


# ---------------------------------------------------------------------------
# Enum membership
# ---------------------------------------------------------------------------


def test_lp_action_membership() -> None:
    expected = {
        "ADD", "INCREASE", "DECREASE", "COLLECT", "REBALANCE",
        "CLOSE", "ZAP_IN", "ZAP_OUT", "MIGRATE",
    }
    assert {m.value for m in LpAction} == expected
    assert len(LpAction) == 9


def test_range_preset_membership() -> None:
    expected = {"FULL", "WIDE", "BALANCED", "TIGHT", "CUSTOM_TICKS", "CUSTOM_PRICE"}
    assert {m.value for m in RangePreset} == expected
    assert len(RangePreset) == 6


def test_lp_strategy_membership() -> None:
    expected = {
        "SPOT", "CURVE", "BID_ASK",
        "MAVERICK_STATIC", "MAVERICK_RIGHT", "MAVERICK_LEFT", "MAVERICK_BOTH",
    }
    assert {m.value for m in LpStrategy} == expected
    assert len(LpStrategy) == 7


def test_amount_mode_membership() -> None:
    expected = {
        "EXACT_USD", "EXACT_TOKEN0", "EXACT_TOKEN1", "EXACT_BOTH",
        "PROPORTIONAL", "PERCENT_OF_POSITION", "ALL",
    }
    assert {m.value for m in AmountMode} == expected
    assert len(AmountMode) == 7


# ---------------------------------------------------------------------------
# Range preset table
# ---------------------------------------------------------------------------


def test_range_preset_bps_table() -> None:
    assert RANGE_PRESET_BPS[RangePreset.FULL] is None
    assert RANGE_PRESET_BPS[RangePreset.WIDE] == 2000
    assert RANGE_PRESET_BPS[RangePreset.BALANCED] == 1000
    assert RANGE_PRESET_BPS[RangePreset.TIGHT] == 500
    assert RANGE_PRESET_BPS[RangePreset.CUSTOM_TICKS] is None
    assert RANGE_PRESET_BPS[RangePreset.CUSTOM_PRICE] is None
    # All presets are covered.
    assert set(RANGE_PRESET_BPS.keys()) == set(RangePreset)


# ---------------------------------------------------------------------------
# Native ↔ wrapped alias map
# ---------------------------------------------------------------------------


def test_weth_native_alias_map_contents() -> None:
    assert WETH_NATIVE_ALIAS_MAP["ETH"] == "WETH"
    assert WETH_NATIVE_ALIAS_MAP["SOL"] == "WSOL"
    assert WETH_NATIVE_ALIAS_MAP["MATIC"] == "WMATIC"
    assert WETH_NATIVE_ALIAS_MAP["POL"] == "WPOL"
    assert WETH_NATIVE_ALIAS_MAP["BNB"] == "WBNB"
    assert WETH_NATIVE_ALIAS_MAP["AVAX"] == "WAVAX"


def test_native_from_wrapped_roundtrip() -> None:
    assert NATIVE_FROM_WRAPPED["WETH"] == "ETH"
    assert NATIVE_FROM_WRAPPED["WSOL"] == "SOL"
    assert NATIVE_FROM_WRAPPED["WBNB"] == "BNB"
    # Every wrapped symbol round-trips to its native form.
    for native, wrapped in WETH_NATIVE_ALIAS_MAP.items():
        assert NATIVE_FROM_WRAPPED[wrapped] == native


# ---------------------------------------------------------------------------
# Pydantic envelope
# ---------------------------------------------------------------------------


def test_liquidity_intent_defaults() -> None:
    intent = LiquidityIntent(action=LpAction.ADD)
    assert intent.action == LpAction.ADD
    assert intent.pair is None
    assert intent.fee_tier is None
    assert intent.deadline_seconds == 600
    assert intent.mev_protection is False
    assert intent.stake_rewards is False
    assert intent.slippage_bps == 50


def test_liquidity_intent_full_construction() -> None:
    intent = LiquidityIntent(
        action=LpAction.ZAP_IN,
        pair=("WETH", "USDC"),
        fee_tier=500,
        tick_spacing=10,
        bin_step=25,
        strategy=LpStrategy.SPOT,
        range_preset=RangePreset.BALANCED,
        range_bounds=(1800.0, 2400.0),
        amount_mode=AmountMode.EXACT_USD,
        amounts={"usd": 5000.0},
        source_token="USDC",
        source_chain="arbitrum",
        deadline_seconds=900,
        mev_protection=True,
        stake_rewards=True,
        slippage_bps=75,
        protocol="uniswap-v3",
        chain="ethereum",
    )
    assert intent.pair == ("WETH", "USDC")
    assert intent.strategy is LpStrategy.SPOT
    assert intent.range_preset is RangePreset.BALANCED
    assert intent.amount_mode is AmountMode.EXACT_USD
    assert intent.amounts == {"usd": 5000.0}


def test_liquidity_intent_roundtrip() -> None:
    original = LiquidityIntent(
        action=LpAction.REBALANCE,
        pair=("WBTC", "WETH"),
        fee_tier=3000,
        strategy=LpStrategy.MAVERICK_RIGHT,
        range_preset=RangePreset.TIGHT,
        amount_mode=AmountMode.PERCENT_OF_POSITION,
        amounts={"percent": 50.0},
        protocol="maverick-v2",
        chain="base",
    )
    dumped = original.model_dump()
    restored = LiquidityIntent.model_validate(dumped)
    assert restored == original
    # Re-dump must be stable.
    assert restored.model_dump() == dumped


def test_liquidity_intent_invalid_enum_raises() -> None:
    with pytest.raises(ValidationError):
        LiquidityIntent(action="NOT_A_REAL_ACTION")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        LiquidityIntent(
            action=LpAction.ADD,
            strategy="NOT_A_STRATEGY",  # type: ignore[arg-type]
        )


def test_liquidity_intent_reexport_from_package() -> None:
    # Spec requires the symbol be importable via the package root.
    from src.agent.intent import LiquidityIntent as Reexport
    from src.agent.intent import LpAction as ReexportAction

    intent = Reexport(action=ReexportAction.CLOSE)
    assert intent.action is LpAction.CLOSE
