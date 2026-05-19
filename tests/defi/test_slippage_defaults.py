"""Tests for centralized DeFi defaults — slippage + deadline.

V7-016: prevents drift back to legacy 100 bps default in adapters.
"""
from __future__ import annotations

import subprocess

from src.defi.defaults import (
    DEFAULT_DEADLINE_SEC,
    DEFAULT_SLIPPAGE_BPS,
    MAX_SLIPPAGE_BPS,
    MIN_SLIPPAGE_BPS,
    clamp_slippage,
)


def test_default_slippage_is_50():
    assert DEFAULT_SLIPPAGE_BPS == 50


def test_default_deadline_is_600():
    assert DEFAULT_DEADLINE_SEC == 600


def test_min_max_bounds():
    assert MIN_SLIPPAGE_BPS == 10
    assert MAX_SLIPPAGE_BPS == 500


def test_clamp_below_min():
    assert clamp_slippage(5) == 10


def test_clamp_at_min():
    assert clamp_slippage(10) == 10


def test_clamp_normal():
    assert clamp_slippage(50) == 50


def test_clamp_at_max():
    assert clamp_slippage(500) == 500


def test_clamp_above_max():
    assert clamp_slippage(600) == 500


def test_no_legacy_100bps_in_adapters():
    """Guard against drift: no `slippage_bps = 100` literal default in src/defi/."""
    import pathlib
    import re

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    pattern = re.compile(r"slippage_bps\s*=\s*100\b")
    hits = []
    for py_path in (repo_root / "src" / "defi").rglob("*.py"):
        for lineno, line in enumerate(py_path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{py_path.relative_to(repo_root)}:{lineno}:{line.strip()}")
    assert not hits, "Legacy 100bps still present in src/defi/:\n" + "\n".join(hits)
