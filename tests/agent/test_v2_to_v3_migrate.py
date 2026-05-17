"""§7 S14 — V2 → V3 migrate detector pin tests.

'Migrate my Uniswap V2 USDC-WETH LP to V3 narrow range' must surface as a
build_yield_execution_plan call with extra.migrate_v2_to_v3=True so the
adapter sequences V2 removeLiquidity → V3 mint.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import _detect_v2_to_v3_migrate, detect_intent


class TestUniswapV2ToV3:
    def test_basic_migrate(self):
        result = _detect_v2_to_v3_migrate(
            "Migrate my Uniswap V2 USDC-WETH LP to V3 narrow range"
        )
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["protocol"] == "uniswap-v3"
        assert args["action"] == "migrate"
        assert args["chain"] == "ethereum"
        assert args["amount_in"] == 0
        extra = args["extra"]
        assert extra["migrate_v2_to_v3"] is True
        assert extra["v2_protocol"] == "uniswap-v2"
        assert extra["v3_protocol"] == "uniswap-v3"
        assert extra["v2_pool"] == "USDC-WETH"
        assert extra["token_a"] == "USDC"
        assert extra["token_b"] == "WETH"
        assert extra["range_kind"] == "narrow"

    def test_with_explicit_range(self):
        result = _detect_v2_to_v3_migrate(
            "Migrate my Uniswap V2 USDC-WETH LP to V3 0.0005 to 0.0008"
        )
        assert result is not None
        _, args = result
        assert args["extra"]["new_range_lower"] == 0.0005
        assert args["extra"]["new_range_upper"] == 0.0008

    def test_dispatch_via_detect_intent(self):
        intent = detect_intent(
            "Migrate my Uniswap V2 USDC-WETH LP to V3 narrow range"
        )
        assert intent is not None
        tool, args = intent
        assert tool == "build_yield_execution_plan"
        assert args["extra"]["migrate_v2_to_v3"] is True


class TestPancakeV2ToV3:
    def test_pancake_defaults_bsc(self):
        result = _detect_v2_to_v3_migrate(
            "Migrate my PancakeSwap V2 CAKE-BNB LP to V3 tight range"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "bsc"
        assert args["protocol"] == "pancakeswap-amm-v3"


class TestChainOverride:
    def test_explicit_chain_arbitrum(self):
        result = _detect_v2_to_v3_migrate(
            "Migrate my Uniswap V2 USDC-WETH LP to V3 narrow range on arbitrum"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "arbitrum"


class TestVerbVariants:
    @pytest.mark.parametrize("verb", ["Migrate", "Move", "Convert", "Upgrade", "Shift"])
    def test_verb_synonyms(self, verb):
        msg = f"{verb} my Uniswap V2 USDC-WETH LP to V3"
        result = _detect_v2_to_v3_migrate(msg)
        assert result is not None


class TestMalformedRejected:
    @pytest.mark.parametrize("msg", [
        "Migrate Uniswap V2",  # no pair
        "Migrate my Uniswap V3 USDC-WETH position 1",  # already V3
        "Migrate my Aave USDC to V3",  # not a v2 DEX
        "Uniswap V2 USDC-WETH LP to V3",  # no verb
        "",
    ])
    def test_malformed_returns_none(self, msg):
        assert _detect_v2_to_v3_migrate(msg) is None
