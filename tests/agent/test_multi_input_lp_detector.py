"""Spec §7 S7 — dust mixing multi-input LP deposit detector.

Asserts `_detect_multi_input_lp` catches multi-token deposit phrasing and
returns a `build_yield_execution_plan` tuple with `extra.input_tokens` set
so the Curve / Balancer / Sanctum adapters can distribute per-coin amounts.

The bug class this guards: prior runtimes had no detector for "use 50 USDC
+ 50 USDT + 50 DAI to deposit to Curve 3pool" and dropped it through to the
generic _detect_aave_supply fallback, which extracted only the last (token,
amount) pair and lost the others — silently sizing the deposit at 1/3 of
the requested principal.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import _detect_multi_input_lp


class TestMultiInputLPDetector:
    def test_catches_three_token_curve_3pool(self):
        msg = "use 50 USDC + 50 USDT + 50 DAI to deposit to Curve 3pool"
        result = _detect_multi_input_lp(msg)
        assert result is not None, "detector must fire on multi-input 3-token phrasing"
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["protocol"] == "curve"
        assert args["action"] == "deposit_lp"
        assert args["asset_in"] == "USDC"  # first captured = primary
        extra = args["extra"]
        toks = extra["input_tokens"]
        # Order-preserving capture: USDC, USDT, DAI each with amount=50.
        assert ("USDC", "50") in toks
        assert ("USDT", "50") in toks
        assert ("DAI", "50") in toks
        assert len(toks) == 3
        assert extra.get("pool_key") == "3pool"

    def test_catches_two_token_short_form(self):
        msg = "50 USDC + 50 USDT to deposit to Curve 3pool"
        result = _detect_multi_input_lp(msg)
        assert result is not None
        _, args = result
        extra = args["extra"]
        toks = extra["input_tokens"]
        assert len(toks) == 2
        assert toks[0][0] == "USDC"
        assert toks[1][0] == "USDT"

    def test_amount_in_is_sum(self):
        msg = "use 100 USDC + 200 USDT to deposit to Curve 3pool"
        _, args = _detect_multi_input_lp(msg)
        # amount_in carries the cumulative deposit size for downstream sizing checks.
        assert float(args["amount_in"]) == 300.0

    def test_chain_hint_is_captured(self):
        msg = "30 USDC + 30 USDT + 30 DAI to deposit to Curve 3pool on optimism"
        _, args = _detect_multi_input_lp(msg)
        assert args["chain"] == "optimism"

    def test_default_chain_is_ethereum(self):
        msg = "50 USDC + 50 USDT + 50 DAI to deposit to Curve 3pool"
        _, args = _detect_multi_input_lp(msg)
        assert args["chain"] == "ethereum"

    def test_does_not_match_single_token(self):
        msg = "deposit 100 USDC to Curve 3pool"
        # Single-token phrasing must NOT trigger multi-input — it falls
        # through to the existing single-asset detectors so they can route.
        assert _detect_multi_input_lp(msg) is None

    def test_does_not_match_swap_phrasing(self):
        msg = "swap 50 USDC for 50 USDT"
        # No 'to/into <pool>' tail → no match.
        assert _detect_multi_input_lp(msg) is None

    def test_balancer_three_token_also_matches(self):
        msg = "use 25 WETH + 25 WBTC + 50 USDC to deposit to Balancer"
        result = _detect_multi_input_lp(msg)
        assert result is not None
        _, args = result
        assert "balancer" in args["protocol"]
        assert len(args["extra"]["input_tokens"]) == 3
