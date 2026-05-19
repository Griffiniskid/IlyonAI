"""Pin tests for V7-013 range_calculator.py spec-path compatibility shim.

Spec ref: ``IlyonAi_LP_Execution_Spec.pdf`` §3.3 (p.6).

The shim at ``src/defi/range_calculator.py`` re-exports the canonical
range helpers from ``src/agent/intent/liquidity_intent.py`` so spec-style
imports continue to resolve. These tests pin:

1. The shim path is importable.
2. Numeric half-widths match the spec (WIDE=2500, BALANCED=1000, TIGHT=500).
3. Shim re-exports are the *same object* as the canonical module — no
   duplication of logic.
"""

from __future__ import annotations


def test_shim_imports_range_preset_bps() -> None:
    """`from src.defi.range_calculator import range_preset_bps` must work."""
    from src.defi.range_calculator import range_preset_bps  # noqa: F401


def test_shim_imports_range_preset_enum() -> None:
    """`from src.defi.range_calculator import RangePreset` must work."""
    from src.defi.range_calculator import RangePreset  # noqa: F401


def test_shim_wide_blue_chip_is_2500_bps() -> None:
    """Spec §3.3 p.6: 'Wide ±25%' → 2500 bps half-width."""
    from src.defi.range_calculator import RangePreset, range_preset_bps

    assert range_preset_bps(RangePreset.WIDE, is_stable_pair=False) == 2500


def test_shim_balanced_blue_chip_is_1000_bps() -> None:
    """Spec §3.3 p.6: 'Balanced ±10%' → 1000 bps half-width."""
    from src.defi.range_calculator import RangePreset, range_preset_bps

    assert range_preset_bps(RangePreset.BALANCED, is_stable_pair=False) == 1000


def test_shim_tight_blue_chip_is_500_bps() -> None:
    """Spec §3.3 p.6: 'Tight ±5%' → 500 bps half-width."""
    from src.defi.range_calculator import RangePreset, range_preset_bps

    assert range_preset_bps(RangePreset.TIGHT, is_stable_pair=False) == 500


def test_shim_function_identity_matches_canonical() -> None:
    """Shim must re-export the SAME function object, not a copy/wrapper.

    Guards against accidental divergence: if someone reimplements the
    body of ``range_preset_bps`` in the shim instead of re-exporting,
    this test fails immediately.
    """
    from src.agent.intent.liquidity_intent import (
        range_preset_bps as canonical_fn,
    )
    from src.defi.range_calculator import range_preset_bps as shim_fn

    assert shim_fn is canonical_fn


def test_shim_enum_identity_matches_canonical() -> None:
    """Same identity guard for the ``RangePreset`` enum class."""
    from src.agent.intent.liquidity_intent import (
        RangePreset as CanonicalRangePreset,
    )
    from src.defi.range_calculator import RangePreset as ShimRangePreset

    assert ShimRangePreset is CanonicalRangePreset


def test_shim_tables_identity_matches_canonical() -> None:
    """Re-exported lookup tables must be the same dicts (no copies)."""
    from src.agent.intent.liquidity_intent import (
        RANGE_PRESET_BPS as canonical_table,
    )
    from src.agent.intent.liquidity_intent import (
        STABLE_RANGE_PRESET_BPS as canonical_stable_table,
    )
    from src.defi.range_calculator import (
        RANGE_PRESET_BPS as shim_table,
    )
    from src.defi.range_calculator import (
        STABLE_RANGE_PRESET_BPS as shim_stable_table,
    )

    assert shim_table is canonical_table
    assert shim_stable_table is canonical_stable_table
