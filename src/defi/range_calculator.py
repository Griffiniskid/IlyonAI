"""V7-013 spec-path compatibility shim — re-exports range helpers from
:mod:`src.agent.intent.liquidity_intent` so spec-style lookups via
``from src.defi.range_calculator import range_preset_bps`` work.

Canonical implementation lives at ``src/agent/intent/liquidity_intent.py``.
This module exists to satisfy spec-mandated import paths without
duplicating logic. See ``IlyonAi_LP_Execution_Spec.pdf`` §3.3 (p.6) for
the numeric ranges:

    Blue-chip pairs: WIDE ±25% (2500 bps), BALANCED ±10% (1000 bps),
                     TIGHT ±5% (500 bps).
    Stable pairs:    WIDE ±0.5% (50 bps),  BALANCED ±0.1% (10 bps),
                     TIGHT ±0.05% (5 bps).
"""

from src.agent.intent.liquidity_intent import (
    RANGE_PRESET_BPS,
    STABLE_RANGE_PRESET_BPS,
    RangePreset,
    range_preset_bps,
)

__all__ = [
    "RangePreset",
    "RANGE_PRESET_BPS",
    "STABLE_RANGE_PRESET_BPS",
    "range_preset_bps",
]
