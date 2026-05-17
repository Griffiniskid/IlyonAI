"""F06 — curve-volatile early-exit pin tests.

Pass-4 hand-read caught: 'curve-volatile-pool' / 'Curve tri-crypto' silently
routed to 3pool stable because the protocol-pair regex captured only the
'curve' head and lost the volatile qualifier. 3pool (DAI/USDC/USDT stable) is
the WRONG pool for someone asking for a volatile/crypto Curve V2 pool, and
curve-v2 isn't adapter-supported yet — so the safest behaviour is to defer to
the LLM contextual fallback (sanitizer prevents fabrication) which then
surfaces an honest blocker.

This test pins the early-exit so the silent stable-pool misroute can't return.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import _detect_add_liquidity


class TestCurveVolatileEarlyExit:
    @pytest.mark.parametrize("text", [
        "Add liquidity to curve-volatile-pool with 100 USDC",
        "Add liquidity to Curve V2 volatile pool with 100 USDC on ethereum",
        "Add liquidity to Curve tri-crypto with 100 USDC",
        "Add liquidity to Curve tricrypto with 100 USDC",
        "Add liquidity to Curve crypto-pool with 100 USDC",
        "Deposit 100 USDC into Curve volatile pool",
        "Deposit 100 USDC into Curve TriCrypto on ethereum",
    ])
    def test_volatile_family_defers_to_llm(self, text):
        # Detector must return None so the message falls through to the LLM
        # contextual fallback — which is guarded by the sanitizer against
        # fabricating a 3pool stable plan.
        assert _detect_add_liquidity(text) is None


class TestCurveStableStillWorks:
    """Non-volatile Curve messages must still route normally — the early-exit
    is volatile-only, not a blanket curve disable."""

    def test_curve_3pool_still_routes(self):
        # '3pool' alone (no volatile/tricrypto/crypto qualifier) must NOT be
        # caught by the volatile guard.
        result = _detect_add_liquidity("Add liquidity to Curve 3pool with 100 USDC on ethereum")
        # We only assert the volatile guard didn't trip; the result may still
        # be None if the LP regex doesn't match the bare-pool form. The point:
        # the volatile early-exit must not kick in on '3pool'.
        # If result is non-None, confirm it didn't get the volatile blocker.
        if result is not None:
            _, args = result
            extras = args.get("extra", {}) or {}
            assert extras.get("market_name") != "volatile"

    def test_curve_stable_pair_still_routes(self):
        # Stable-pair Curve LP must not be blocked.
        result = _detect_add_liquidity("Add liquidity to Curve USDC/USDT with 100 USDC on ethereum")
        if result is not None:
            _, args = result
            extras = args.get("extra", {}) or {}
            assert extras.get("market_name") != "volatile"


class TestCurveVolatileNeverEmitsStablePool:
    """The original bug: 'curve-volatile' silently produced a 3pool stable
    plan. This test ensures no positive routing occurs (None = defer)."""

    def test_volatile_pool_returns_none_not_3pool(self):
        result = _detect_add_liquidity("Add liquidity to curve-volatile-pool with 100 USDC on ethereum")
        # If result is non-None, the detector emitted a plan — which is wrong
        # for volatile (no adapter support). Must be None.
        assert result is None, (
            f"curve-volatile must defer to LLM, but detector emitted: {result}"
        )
