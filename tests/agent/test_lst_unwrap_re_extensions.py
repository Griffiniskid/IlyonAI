"""V7-070 — LST → LP detector pin tests.

Pins three phrasings:
  1. Existing supply-form still matches (regression guard).
  2. Compact arrow form: 'wstETH → ETH/USDC LP'.
  3. H10 imperative form: 'Take my 5 wstETH and put into ETH+USDC'.

Forms 2-3 route to a new _detect_lst_to_lp branch that emits a deposit_lp
plan with extra.prep_swap unwrapping wstETH → WETH (Curve) and
extra.lp_target_pair carrying the two pool sides.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import (
    _detect_lst_to_lp,
    _detect_lst_unwrap_chain,
    detect_intent,
)


class TestExistingSupplyPathUnchanged:
    """Regression guard — the original 'Use my X stETH to deposit to PROTO'
    contract from §7 S10 must still produce an Aave V3 supply plan."""

    def test_steth_to_aave_v3_still_matches(self):
        result = _detect_lst_unwrap_chain(
            "Use my 0.05 stETH to deposit to Aave V3"
        )
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["action"] == "supply"
        assert args["asset_in"] == "WETH"
        assert args["extra"]["prep_swap"] == [("STETH", "WETH", "curve")]


class TestArrowFormToLP:
    """V7-070 — 'wstETH → ETH/USDC LP' compact form."""

    @pytest.mark.parametrize("arrow", ["→", "->", "to", "into"])
    def test_arrow_variants(self, arrow):
        msg = f"wstETH {arrow} ETH/USDC LP"
        result = _detect_lst_to_lp(msg)
        assert result is not None, (
            f"V7-070 — arrow form must match for separator {arrow!r}"
        )
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["action"] == "deposit_lp"
        assert args["extra"]["source_token"] == "WSTETH"
        # Curve is the registered wstETH→WETH venue.
        assert args["extra"]["prep_swap"] == [("WSTETH", "WETH", "curve")]
        # Pair is normalised (sorted) so {ETH,USDC} routes deterministically.
        assert set(args["extra"]["lp_target_pair"]) == {"ETH", "USDC"}
        assert args["extra"]["lst_to_lp"] is True

    def test_plus_separator(self):
        result = _detect_lst_to_lp("wstETH → ETH+USDC LP")
        assert result is not None
        _, args = result
        assert set(args["extra"]["lp_target_pair"]) == {"ETH", "USDC"}


class TestH10ImperativeForm:
    """V7-070 — 'Take my N wstETH and put/split into ETH+USDC'."""

    @pytest.mark.parametrize("phrasing,amount", [
        ("Take my 5 wstETH and put into ETH+USDC",        "5"),
        ("Take my 5 wstETH and split into ETH+USDC",      "5"),
        ("Take my 2.5 wstETH and deposit into ETH/USDC",  "2.5"),
        ("Use my 1 wstETH and provide into ETH+USDC",     "1"),
    ])
    def test_h10_variants(self, phrasing, amount):
        result = _detect_lst_to_lp(phrasing)
        assert result is not None, (
            f"V7-070 — H10 form must match: {phrasing!r}"
        )
        _, args = result
        assert args["action"] == "deposit_lp"
        assert args["amount_in"] == amount
        assert args["extra"]["source_token"] == "WSTETH"
        assert args["extra"]["source_amount"] == amount
        assert set(args["extra"]["lp_target_pair"]) == {"ETH", "USDC"}

    def test_dispatch_via_detect_intent(self):
        """The runtime dispatcher must route H10 LST→LP prompts to
        _detect_lst_to_lp ahead of the supply-only _lst_unwrap path so
        wstETH→pair phrasings emit deposit_lp, not supply."""
        intent = detect_intent(
            "Take my 5 wstETH and put into ETH+USDC"
        )
        assert intent is not None
        tool, args = intent
        assert tool == "build_yield_execution_plan"
        assert args["action"] == "deposit_lp", (
            f"V7-070 — must route to deposit_lp; got action={args.get('action')}"
        )
        assert args["extra"].get("lst_to_lp") is True


class TestNonLSTRejected:
    """Conservative: tokens not in the LST whitelist must not false-match."""

    @pytest.mark.parametrize("msg", [
        "USDC → ETH/USDT LP",
        "Take my 100 USDC and put into ETH+USDT",
        "Take my 5 BTC and put into ETH+USDC",
    ])
    def test_non_lst_returns_none(self, msg):
        assert _detect_lst_to_lp(msg) is None


class TestMalformedRejected:
    @pytest.mark.parametrize("msg", [
        "wstETH",
        "wstETH → USDC",          # only one pool side
        "Take my wstETH and put into ETH+USDC",  # no amount
        "",
    ])
    def test_malformed_returns_none(self, msg):
        assert _detect_lst_to_lp(msg) is None
