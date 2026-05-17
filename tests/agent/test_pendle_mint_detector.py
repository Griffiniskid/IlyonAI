"""F04 — _detect_pendle_mint pin tests.

Pass-4 hand-read caught: 'Pendle mint PT-USDe with 100 USDC' silently routed
to morpho-blue via _detect_generic_supply (Pendle is in the generic supply
alternation; 'mint' was swallowed like a 'supply' verb). Pendle mint creates
PT/YT splits — semantically different from a lending supply. These tests pin
the routing to build_yield_execution_plan with protocol=pendle-v2 and assert
the morpho-blue misroute can never reappear.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import (
    _detect_pendle_mint,
    _detect_generic_supply,
)


class TestPendleMintCanonicalForm:
    def test_pendle_mint_pt_usde_with_amount(self):
        result = _detect_pendle_mint("Pendle mint PT-USDe with 100 USDC")
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["protocol"] == "pendle-v2"
        assert args["action"] == "mint_py"
        assert args["asset_in"] == "USDC"
        assert float(args["amount_in"]) == 100.0
        assert args["chain"] == "ethereum"
        assert args["extra"]["market_symbol"] == "PT-USDe"

    def test_mint_pt_on_pendle_form(self):
        result = _detect_pendle_mint("Mint PT-USDe on Pendle with 50 USDC")
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["protocol"] == "pendle-v2"
        assert args["extra"]["market_symbol"] == "PT-USDe"

    def test_pendle_swap_to_pt(self):
        result = _detect_pendle_mint("Pendle swap to PT-USDe with 100 USDC")
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["action"] == "swap_for_pt"
        assert args["protocol"] == "pendle-v2"


class TestPendleMintDoesNotMisroute:
    """The morpho-blue silent route is the bug — these tests pin it dead."""

    def test_pendle_mint_does_not_return_morpho_blue(self):
        result = _detect_pendle_mint("Pendle mint PT-USDe with 100 USDC")
        assert result is not None
        _, args = result
        assert args["protocol"] != "morpho-blue"
        assert args["protocol"] != "morpho"

    def test_generic_supply_would_have_caught_morpho_now_pendle_wins(self):
        # Generic-supply might still trip on the same message, but the
        # dispatch order (pendle detector runs first) ensures it never
        # reaches generic-supply. We verify pendle's detector emits the
        # right tuple — the dispatch wiring is asserted separately.
        result = _detect_pendle_mint("Pendle mint PT-USDe with 100 USDC")
        assert result is not None
        assert result[1]["protocol"] == "pendle-v2"


class TestPendleMintGating:
    def test_requires_pendle_keyword(self):
        # No 'pendle' word → detector refuses.
        assert _detect_pendle_mint("mint PT-USDe with 100 USDC") is None

    def test_requires_pt_yt_or_mint_signal(self):
        # 'pendle' alone with no PT/YT/mint/market signal → refuses.
        assert _detect_pendle_mint("tell me about pendle") is None

    def test_solana_chain_defers_to_llm(self):
        # Pendle is EVM-only; explicit "on solana" must defer (return None)
        # so the LLM contextual fallback / blocker path surfaces it.
        result = _detect_pendle_mint("Pendle mint PT-USDe with 100 USDC on solana")
        assert result is None

    def test_explicit_arbitrum_chain_captured(self):
        result = _detect_pendle_mint("Pendle mint PT-eETH with 50 ETH on arbitrum")
        assert result is not None
        _, args = result
        assert args["chain"] == "arbitrum"


class TestPendleDispatchOrder:
    """Pendle detector must be wired BEFORE _detect_generic_supply in the
    dispatch tuple so the morpho-blue misroute can never reappear."""

    def test_pendle_before_generic_supply_in_dispatch(self):
        # Read the source and assert ordering.
        import inspect
        from src.agent import simple_runtime
        src = inspect.getsource(simple_runtime)
        # Find the dispatch tuple line containing both detectors.
        line = [ln for ln in src.splitlines()
                if "_detect_pendle_mint" in ln and "_detect_generic_supply" in ln]
        assert line, "dispatch tuple containing both detectors not found"
        idx_pendle = line[0].index("_detect_pendle_mint")
        idx_generic = line[0].index("_detect_generic_supply")
        assert idx_pendle < idx_generic, (
            "pendle detector must precede generic_supply to shadow morpho misroute"
        )
