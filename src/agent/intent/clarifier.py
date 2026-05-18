"""LP intent clarifier — V7 §1 gap.

Inspects a :class:`LiquidityIntent` and returns user-facing clarifier text
when required slots are missing. Returns ``None`` when the intent has
everything the LP planner needs to proceed.

The check is intentionally conservative — we only emit a clarifier when
the planner would otherwise have to invent a value (pair, amount, fee
tier, range). Optional fields (slippage, deadline, MEV) all carry sane
defaults on the envelope and are not gated here.
"""
from __future__ import annotations

from typing import Optional

from .liquidity_intent import LiquidityIntent, LpAction


__all__ = ["needs_clarification"]


def needs_clarification(intent: LiquidityIntent) -> Optional[str]:
    """Return a user-facing clarifier string if ``intent`` is ambiguous.

    Returns ``None`` when the intent is fully specified for its action.

    Rules (spec §1):
      * ADD/INCREASE/ZAP_IN — need pair AND amounts AND
        (fee_tier OR range_preset OR bin_step).
      * DECREASE/CLOSE/ZAP_OUT — need pair (the position to act on).
      * REBALANCE — need pair AND a target range_preset or range_bounds.
      * MIGRATE — need pair AND a target protocol.
      * COLLECT — no clarifier; collecting fees never needs amount.
    """
    if intent.action in (LpAction.ADD, LpAction.INCREASE, LpAction.ZAP_IN):
        if not intent.pair:
            return "Which pair and amount?"
        if not intent.amounts:
            return "Which pair and amount?"
        if (
            intent.fee_tier is None
            and intent.range_preset is None
            and intent.bin_step is None
        ):
            return "Which fee tier (0.05%/0.30%/1%) or range?"
        return None

    if intent.action in (LpAction.DECREASE, LpAction.CLOSE, LpAction.ZAP_OUT):
        if not intent.pair:
            return "Which position (pair) do you want to act on?"
        return None

    if intent.action == LpAction.REBALANCE:
        if not intent.pair:
            return "Which position (pair) do you want to rebalance?"
        if intent.range_preset is None and intent.range_bounds is None:
            return "Which target range (TIGHT/BALANCED/WIDE or explicit bounds)?"
        return None

    if intent.action == LpAction.MIGRATE:
        if not intent.pair:
            return "Which position (pair) do you want to migrate?"
        if not intent.protocol:
            return "Which protocol do you want to migrate to?"
        return None

    # COLLECT and anything unknown — let the planner proceed.
    return None
