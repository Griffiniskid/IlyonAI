"""§7 S10 — pre-deposited LST unwrap chain detector pin tests.

'Use my 0.05 stETH to deposit to Aave V3' must surface as a two-leg plan:
  1. Curve stETH→WETH swap (prep_swap)
  2. Aave V3 WETH supply

Adapter layer consumes extra.prep_swap=[(token_in, token_out, dex)] and chains
the calldata. The detector only assembles the params dict; the build path is
covered by build_yield_execution_plan integration tests.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import (
    _detect_lst_unwrap_chain,
    detect_intent,
)


class TestStETHToAaveV3:
    def test_steth_to_aave_v3_default_ethereum(self):
        result = _detect_lst_unwrap_chain("Use my 0.05 stETH to deposit to Aave V3")
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["chain"] == "ethereum"
        assert args["protocol"] == "aave-v3"
        assert args["action"] == "supply"
        assert args["asset_in"] == "WETH"
        assert args["amount_in"] == "0.05"
        extra = args["extra"]
        assert extra["prep_swap"] == [("STETH", "WETH", "curve")]
        assert extra["source_token"] == "STETH"
        assert extra["source_amount"] == "0.05"

    def test_dispatch_via_detect_intent(self):
        # Confirm the detector wins over _detect_enso_vault_deposit in the
        # runtime tuple — Enso would otherwise route stETH→aave-v3 as a
        # direct supply with asset_in=STETH (which Aave rejects).
        intent = detect_intent("Use my 0.05 stETH to deposit to Aave V3")
        assert intent is not None
        tool, args = intent
        assert tool == "build_yield_execution_plan"
        assert args["asset_in"] == "WETH", (
            f"Expected unwrapped WETH; got {args.get('asset_in')} — "
            f"_detect_enso_vault_deposit likely swallowed the prompt."
        )
        assert "prep_swap" in args.get("extra", {})


class TestOtherLSTs:
    @pytest.mark.parametrize("lst,target,dex", [
        ("rETH",   "WETH", "curve"),
        ("eETH",   "WETH", "curve"),
        ("weETH",  "WETH", "curve"),
        ("ezETH",  "WETH", "balancer"),
        ("rsETH",  "WETH", "balancer"),
        ("mETH",   "WETH", "curve"),
        ("frxETH", "WETH", "curve"),
        ("sfrxETH","FRXETH", "curve"),
    ])
    def test_all_supported_lsts(self, lst, target, dex):
        msg = f"Use my 1 {lst} to supply to Compound V3"
        result = _detect_lst_unwrap_chain(msg)
        assert result is not None, f"detector should match {lst} prompt"
        _, args = result
        assert args["asset_in"] == target
        assert args["extra"]["prep_swap"] == [(lst.upper(), target, dex)]


class TestNonLSTRejected:
    @pytest.mark.parametrize("token", ["USDC", "USDT", "DAI", "WBTC", "SOL"])
    def test_non_lst_falls_through(self, token):
        # Non-LST tokens must return None so the standard supply path handles them.
        msg = f"Use my 100 {token} to deposit to Aave V3"
        assert _detect_lst_unwrap_chain(msg) is None


class TestChainOverride:
    def test_arbitrum_explicit(self):
        result = _detect_lst_unwrap_chain(
            "Use my 0.5 wstETH to supply to Aave V3 on Arbitrum"
        )
        # wstETH not in _LST_UNWRAP_TOKENS — falls through. That's correct:
        # wstETH IS accepted by Aave V3 directly.
        assert result is None

    def test_optimism_via_velodrome_phrase(self):
        result = _detect_lst_unwrap_chain(
            "Use my 0.1 stETH to deposit to Compound V3 on Optimism"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "optimism"
        assert args["protocol"] == "compound-v3"


class TestMalformedRejected:
    @pytest.mark.parametrize("msg", [
        "Use stETH",
        "Use my stETH to deposit to Aave V3",  # no amount
        "Use my 0.05 stETH to deposit",  # no protocol
        "stETH to Aave V3",
        "",
    ])
    def test_malformed_returns_none(self, msg):
        assert _detect_lst_unwrap_chain(msg) is None
