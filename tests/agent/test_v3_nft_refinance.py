"""§7 S11 — NFT-locked LP refinance close+reopen detector pin tests.

'Refinance my Uniswap V3 USDC-WETH position 12345 with tighter range' must
emit a build_yield_execution_plan call with extra.refinance=True so the
adapter layer assembles the (decreaseLiquidity+collect+burn) → (mint) pair.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import _detect_v3_nft_refinance, detect_intent


class TestUniswapV3Refinance:
    def test_basic_refinance(self):
        result = _detect_v3_nft_refinance(
            "Refinance my Uniswap V3 USDC-WETH position 12345 with tighter range"
        )
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["protocol"] == "uniswap-v3"
        assert args["action"] == "refinance"
        assert args["chain"] == "ethereum"
        extra = args["extra"]
        assert extra["refinance"] is True
        assert extra["token_id"] == "12345"
        assert extra["pool_symbol"] == "USDC-WETH"
        assert extra["token_a"] == "USDC"
        assert extra["token_b"] == "WETH"
        assert extra["range_kind"] == "tighter"

    def test_refinance_with_explicit_range(self):
        result = _detect_v3_nft_refinance(
            "Refinance my Uniswap V3 USDC-WETH position 99 with range 0.95 to 1.05"
        )
        assert result is not None
        _, args = result
        extra = args["extra"]
        assert extra["new_range_lower"] == 0.95
        assert extra["new_range_upper"] == 1.05

    def test_dispatch_via_detect_intent(self):
        intent = detect_intent(
            "Refinance my Uniswap V3 USDC-WETH position 12345 with tighter range"
        )
        assert intent is not None
        tool, args = intent
        assert tool == "build_yield_execution_plan"
        assert args["action"] == "refinance"
        assert args["extra"]["token_id"] == "12345"


class TestOtherProtocols:
    def test_pancakeswap_v3_defaults_bsc(self):
        result = _detect_v3_nft_refinance(
            "Refinance my PancakeSwap V3 CAKE-BNB position 7"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "bsc"
        assert args["protocol"] == "pancakeswap-amm-v3"

    def test_aerodrome_slipstream_defaults_base(self):
        result = _detect_v3_nft_refinance(
            "Refinance my Aerodrome Slipstream WETH-USDC position 4242"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "base"
        assert args["protocol"] == "aerodrome-slipstream"

    def test_velodrome_slipstream_defaults_optimism(self):
        result = _detect_v3_nft_refinance(
            "Refinance my Velodrome Slipstream OP-USDC position 1"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "optimism"

    def test_explicit_chain_override(self):
        result = _detect_v3_nft_refinance(
            "Refinance my Uniswap V3 USDC-WETH position 1 on arbitrum"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "arbitrum"


class TestMalformedRejected:
    @pytest.mark.parametrize("msg", [
        "Refinance Uniswap V3",  # no position id
        "Refinance my Uniswap V3 USDC position 1",  # bad pair (single token)
        "Refinance my position 1",  # no protocol
        "Uniswap V3 USDC-WETH position 12345",  # no verb
        "",
    ])
    def test_malformed_returns_none(self, msg):
        assert _detect_v3_nft_refinance(msg) is None
