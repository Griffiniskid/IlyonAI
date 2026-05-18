"""V7 §1 — pin tests for LP intent clarifier."""
from __future__ import annotations

from src.agent.intent.clarifier import needs_clarification
from src.agent.intent.liquidity_intent import (
    LiquidityIntent,
    LpAction,
    RangePreset,
)


def _add(**overrides):
    base = dict(
        action=LpAction.ADD,
        pair=("USDC", "WETH"),
        amounts={"usd": 1000.0},
        fee_tier=500,
    )
    base.update(overrides)
    return LiquidityIntent(**base)


def test_add_complete_no_clarifier():
    intent = _add()
    assert needs_clarification(intent) is None


def test_add_missing_pair_asks():
    intent = LiquidityIntent(action=LpAction.ADD)
    assert needs_clarification(intent) == "Which pair and amount?"


def test_add_missing_fee_and_range_asks():
    intent = _add(fee_tier=None)
    assert "fee tier" in needs_clarification(intent)


def test_add_with_range_preset_ok():
    intent = _add(fee_tier=None, range_preset=RangePreset.BALANCED)
    assert needs_clarification(intent) is None


def test_decrease_needs_pair():
    intent = LiquidityIntent(action=LpAction.DECREASE)
    assert needs_clarification(intent) == "Which position (pair) do you want to act on?"


def test_close_with_pair_ok():
    intent = LiquidityIntent(action=LpAction.CLOSE, pair=("USDC", "WETH"))
    assert needs_clarification(intent) is None


def test_rebalance_needs_range():
    intent = LiquidityIntent(action=LpAction.REBALANCE, pair=("USDC", "WETH"))
    assert "range" in needs_clarification(intent).lower()


def test_migrate_needs_protocol():
    intent = LiquidityIntent(action=LpAction.MIGRATE, pair=("USDC", "WETH"))
    assert needs_clarification(intent) == "Which protocol do you want to migrate to?"


def test_collect_never_needs_clarifier():
    intent = LiquidityIntent(action=LpAction.COLLECT)
    assert needs_clarification(intent) is None
