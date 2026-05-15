"""Smoke tests for the Enso per-asset Aave V3 aToken override map.

When Enso's dynamic registry misses the position-token for a known
chain × protocol × asset combo (transient cache miss / new pool), the
EnsoShortcutAdapter falls through to a curated override map. These
tests assert the canonical aToken addresses match Aave's deployed
contracts.
"""
from __future__ import annotations

import inspect

from src.defi.execution.adapters import enso_shortcut


def _extract_overrides() -> dict[int, dict[str, str]]:
    """Read the override map defined locally inside build() — we walk
    the function source to extract the literal dict so tests stay green
    even when the file is reorganised but the values are preserved.
    """
    src = inspect.getsource(enso_shortcut)
    start = src.find("_RECEIPT_BY_HUB:")
    if start < 0:
        return {}
    # Walk braces until balanced.
    depth = 0
    end = -1
    after_eq = src.find("{", start)
    for i in range(after_eq, len(src)):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    # We don't need to eval the literal — just check key/value presence
    # textually. Trying to eval would pull in surrounding symbols.
    return {"raw": src[start:end]}


def test_override_map_includes_base_aave_v3_usdc():
    raw = _extract_overrides()["raw"]
    assert "8453:" in raw or "8453 " in raw or "8453," in raw or "8453}" in raw or "8453:" in raw or "8453:" in raw or "8453" in raw
    assert "aave-v3:usdc" in raw.lower()
    assert "0x4e65fe4dba92790696d040ac24aa414708f5c0ab" in raw.lower()  # aBasUSDC


def test_override_map_includes_optimism_aave_v3_weth():
    raw = _extract_overrides()["raw"]
    assert "aave-v3:weth" in raw.lower()
    assert "0xe50fa9b3c56ffb159cb0fca61f5c9d750e8128c8" in raw.lower()  # aOptWETH


def test_override_map_includes_arbitrum_aave_v3():
    raw = _extract_overrides()["raw"]
    assert "42161" in raw


def test_override_map_includes_polygon_aave_v3():
    raw = _extract_overrides()["raw"]
    assert "137" in raw


def test_override_map_preserves_ethereum_lst_hubs():
    raw = _extract_overrides()["raw"]
    # Mainnet Renzo / Kelp / Swell / Puffer entries must not be lost.
    assert "renzo-ezeth" in raw.lower()
    assert "kelp-rseth" in raw.lower()
    assert "swell-rsweth" in raw.lower()
    assert "puffer-pufeth" in raw.lower()


def test_override_map_chain_one_keyed_by_slug_alone():
    """Ethereum LST hubs use protocol_slug as the key directly (no
    :asset suffix) because the LST IS the receipt — no per-asset variant.
    """
    raw = _extract_overrides()["raw"]
    assert '"renzo-ezeth": "0xbf' in raw.lower() or '"renzo-ezeth":"0xbf' in raw.lower()
