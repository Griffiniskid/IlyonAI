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
# Stable-pair range presets — spec §3.3:
#   "Stable pairs use ±0.5% / ±0.1% / ±0.05%."
# Stable LP concentrates almost all liquidity in a very thin band around
# 1.0 because the pair is engineered to peg. Using the blue-chip ±25%
# preset on a USDC/USDT pool would deploy ~98% of capital outside the
# high-utilisation band and earn near-zero fees.
# ---------------------------------------------------------------------------

STABLE_RANGE_PRESET_BPS: dict[RangePreset, Optional[int]] = {
    RangePreset.FULL: None,
    RangePreset.WIDE: 50,        # ±0.5%
    RangePreset.BALANCED: 10,    # ±0.1%
    RangePreset.TIGHT: 5,        # ±0.05%
    RangePreset.CUSTOM_TICKS: None,
    RangePreset.CUSTOM_PRICE: None,
}


# ---------------------------------------------------------------------------
# Stable-pair detection token set (shared with fee-tier defaults).
# Imported lazily inside ``is_stable_pair`` to avoid a circular import:
# ``src.defi.fee_tier_defaults`` is the single source of truth.
# ---------------------------------------------------------------------------


def is_stable_pair(token0: Optional[str], token1: Optional[str]) -> bool:
    """Return True iff *both* sides of the pair are USD-pegged stables.

    Uses the canonical ``STABLE_TOKENS`` set from
    :mod:`src.defi.fee_tier_defaults` so the two helpers stay in sync.
    Case-insensitive; bridge-suffix variants (``USDC.e``) are honoured.
    """
    if not token0 or not token1:
        return False
    # Local import keeps this module dependency-light at import time.
    from src.defi.fee_tier_defaults import STABLE_TOKENS

    return (
        token0.strip().upper() in STABLE_TOKENS
        and token1.strip().upper() in STABLE_TOKENS
    )


def range_preset_bps(
    preset: RangePreset, *, is_stable_pair: bool = False
) -> Optional[int]:
    """Resolve the half-width (in bps) for a given preset + pair category.

    Spec §3.3:
      - Blue-chip pairs: ±25% / ±10% / ±5%  (WIDE / BALANCED / TIGHT)
      - Stable pairs:    ±0.5% / ±0.1% / ±0.05%

    ``FULL`` and ``CUSTOM_*`` always return ``None`` (unbounded or
    caller-supplied bounds).
    """
    table = STABLE_RANGE_PRESET_BPS if is_stable_pair else RANGE_PRESET_BPS
    return table.get(preset)


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
    "STABLE_RANGE_PRESET_BPS",
    "is_stable_pair",
    "range_preset_bps",
    "WETH_NATIVE_ALIAS_MAP",
    "NATIVE_FROM_WRAPPED",
]
