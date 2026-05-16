"""Pin _LP_TOP_ONE_RE unit capture rejects continuation modifiers.

v4-A01 turn 3 caught: 'Use $250 instead' captured unit='instead', which
became asset_in='INSTEAD'. Aave V3 adapter then raised
'no token metadata for INSTEAD on base'. _NON_ASSET_UNITS must reject
common continuation modifiers in addition to USD denominators.
"""
from __future__ import annotations


def test_non_asset_units_includes_modifiers():
    """_NON_ASSET_UNITS must reject continuation words."""
    # Inline the set to pin the contract (no public symbol export — only
    # used inside run_ephemeral_turn).
    expected = {
        "USD", "$", "DOLLARS", "K", "M", "B", "BUCKS",
        "INSTEAD", "NOW", "THEN", "PLEASE", "AGAIN",
        "TODAY", "TONIGHT", "TOMORROW", "ASAP",
    }
    from pathlib import Path
    src = Path(__file__).parent.parent.parent / "src" / "agent" / "simple_runtime.py"
    text = src.read_text()
    # Find the set literal and ensure expected keys are present.
    assert "_NON_ASSET_UNITS = {" in text
    for word in expected:
        assert f'"{word}"' in text, f"_NON_ASSET_UNITS missing {word!r}"
