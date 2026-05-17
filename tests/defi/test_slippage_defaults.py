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
    try:
        out = subprocess.check_output(
            ["grep", "-rnE", r"slippage_bps\s*=\s*100\b", "src/defi/"],
            cwd="/home/griffiniskid/Documents/ai-sentinel/",
        )
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            return  # zero matches = success
        raise
    raise AssertionError(f"Legacy 100bps still present in src/defi/:\n{out.decode()}")
