"""Typed liquidity-provision (LP) intent envelope.

Spec ref: ``IlyonAi_LP_Execution_Spec.pdf`` §3.

This module defines the structured intent envelope produced by the LP
intent detector and consumed by downstream LP planners / executors. It is
intentionally separate from :mod:`src.agent.intent.defi_intent` which
covers search / allocation intents over yield opportunities.

The envelope is pydantic v2; everything is ``Optional`` so that callers
can incrementally fill it as the conversation provides more constraints.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums (spec §3 — typed LP intent envelope)
# ---------------------------------------------------------------------------


class LpAction(str, Enum):
    """High-level LP lifecycle action the user is requesting."""

    ADD = "ADD"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    COLLECT = "COLLECT"
    REBALANCE = "REBALANCE"
    CLOSE = "CLOSE"
    ZAP_IN = "ZAP_IN"
    ZAP_OUT = "ZAP_OUT"
    MIGRATE = "MIGRATE"


class RangePreset(str, Enum):
    """Concentrated-liquidity range preset.

    ``FULL`` covers ``[0, ∞)`` and is represented by ``None`` in
    :data:`RANGE_PRESET_BPS`. ``CUSTOM_TICKS`` / ``CUSTOM_PRICE`` mean the
    caller will populate :attr:`LiquidityIntent.range_bounds` directly.
    """

    FULL = "FULL"
    WIDE = "WIDE"
    BALANCED = "BALANCED"
    TIGHT = "TIGHT"
    CUSTOM_TICKS = "CUSTOM_TICKS"
    CUSTOM_PRICE = "CUSTOM_PRICE"


class LpStrategy(str, Enum):
    """Per-bin / per-curve distribution strategy.

    SPOT/CURVE/BID_ASK map to Meteora DLMM and similar bin-based AMMs.
    ``MAVERICK_*`` map to Maverick Protocol mode IDs (Static / Right /
    Left / Both).
    """

    SPOT = "SPOT"
    CURVE = "CURVE"
    BID_ASK = "BID_ASK"
    MAVERICK_STATIC = "MAVERICK_STATIC"
    MAVERICK_RIGHT = "MAVERICK_RIGHT"
    MAVERICK_LEFT = "MAVERICK_LEFT"
    MAVERICK_BOTH = "MAVERICK_BOTH"


class AmountMode(str, Enum):
    """How the caller specified the amount(s) to deploy / withdraw."""

    EXACT_USD = "EXACT_USD"
    EXACT_TOKEN0 = "EXACT_TOKEN0"
    EXACT_TOKEN1 = "EXACT_TOKEN1"
    EXACT_BOTH = "EXACT_BOTH"
    PROPORTIONAL = "PROPORTIONAL"
    PERCENT_OF_POSITION = "PERCENT_OF_POSITION"
    ALL = "ALL"


# ---------------------------------------------------------------------------
# Range preset → half-width in basis points (1 bp = 0.01 %).
# ``None`` means either unbounded (FULL) or caller-supplied (CUSTOM_*).
# ---------------------------------------------------------------------------

RANGE_PRESET_BPS: dict[RangePreset, Optional[int]] = {
    RangePreset.FULL: None,
    # Spec §3.3 (PDF p.6): "Wide ±25% (~4× efficiency, ~95% in-range
    # historically for blue-chips)" → 2500 bps half-width.
    RangePreset.WIDE: 2500,
    RangePreset.BALANCED: 1000,
    RangePreset.TIGHT: 500,
    RangePreset.CUSTOM_TICKS: None,
    RangePreset.CUSTOM_PRICE: None,
}


# ---------------------------------------------------------------------------
# Native ↔ wrapped alias map. The LP planner normalises pair symbols to
# their wrapped form because every AMM trades the wrapped token.
# ---------------------------------------------------------------------------

WETH_NATIVE_ALIAS_MAP: dict[str, str] = {
    "ETH": "WETH",
    "MATIC": "WMATIC",
    "POL": "WPOL",
    "BNB": "WBNB",
    "AVAX": "WAVAX",
    "FTM": "WFTM",
    "S": "WS",
    "BERA": "WBERA",
    "CELO": "CELO",
    "XDAI": "WXDAI",
    "MNT": "WMNT",
    "SOL": "WSOL",
}

NATIVE_FROM_WRAPPED: dict[str, str] = {v: k for k, v in WETH_NATIVE_ALIAS_MAP.items()}


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


class LiquidityIntent(BaseModel):
    """Typed LP intent envelope (spec §3).

    Every field is optional so the detector can progressively fill the
    envelope as the user provides more constraints. The downstream
    planner is responsible for refusing under-specified intents.
    """

    action: LpAction = Field(..., description="LP lifecycle action.")
    pair: Optional[tuple[str, str]] = Field(
        default=None,
        description="(token0_sym, token1_sym) — wrapped form preferred.",
    )
    fee_tier: Optional[int] = Field(
        default=None,
        description="Fee tier in 1e-6 units (e.g. 500 = 0.05%).",
    )
    tick_spacing: Optional[int] = Field(
        default=None,
        description="Concentrated-liquidity tick spacing.",
    )
    bin_step: Optional[int] = Field(
        default=None,
        description="DLMM / Maverick bin step in bps.",
    )
    strategy: Optional[LpStrategy] = Field(
        default=None,
        description="Bin distribution / curve shape strategy.",
    )
    range_preset: Optional[RangePreset] = Field(
        default=None,
        description="Range preset (see RANGE_PRESET_BPS).",
    )
    range_bounds: Optional[tuple[float, float]] = Field(
        default=None,
        description="(lower, upper) in price or tick space.",
    )
    amount_mode: Optional[AmountMode] = Field(
        default=None,
        description="How amounts were specified.",
    )
    amounts: Optional[dict[str, float]] = Field(
        default=None,
        description='Concrete amounts, e.g. {"token0": .., "token1": .., "usd": ..}.',
    )
    source_token: Optional[str] = Field(
        default=None,
        description="Source token for zap-in flows.",
    )
    source_chain: Optional[str] = Field(
        default=None,
        description="Source chain for cross-chain LP flows.",
    )
    deadline_seconds: int = Field(
        default=600,
        description="Tx deadline window in seconds.",
    )
    mev_protection: bool = Field(
        default=False,
        description="Route through MEV-protected RPC / bundle.",
    )
    stake_rewards: bool = Field(
        default=False,
        description="Auto-stake earned LP tokens / rewards.",
    )
    slippage_bps: int = Field(
        default=50,
        description="Slippage tolerance in basis points (1 bp = 0.01%).",
    )
    protocol: Optional[str] = Field(
        default=None,
        description="Protocol slug (e.g. 'uniswap-v3', 'meteora-dlmm').",
    )
    chain: Optional[str] = Field(
        default=None,
        description="Chain slug (e.g. 'ethereum', 'solana').",
    )


__all__ = [
    "LpAction",
    "RangePreset",
    "LpStrategy",
    "AmountMode",
    "LiquidityIntent",
    "RANGE_PRESET_BPS",
    "WETH_NATIVE_ALIAS_MAP",
    "NATIVE_FROM_WRAPPED",
]
