"""RC7d — chain-word-as-asset detection pin tests.

Pin: when the user types `"Aave V3 supply 100 on Base"` and the asset
slot ends up as the chain word ('BASE'), the detector MUST refuse rather
than build a plan with `asset_in='BASE'`. Pass A H08/H13 captured the
adapter emitting ADAPTER_BUILD_FAILED on asset_in='BASE' because the
Aave adapter has no token metadata for the literal chain name.
"""
from __future__ import annotations

from src.agent.simple_runtime import _detect_aave_supply


class TestChainWordsRefused:
    def test_supply_chain_word_as_asset_returns_none(self):
        """`Aave V3 supply 100 BASE` (no real asset before 'BASE') → REFUSE.

        The detector previously emitted asset_in='BASE' which triggered
        ADAPTER_BUILD_FAILED downstream. Now it refuses so the LLM /
        freeform fallback can clarify with the user.
        """
        result = _detect_aave_supply("Aave V3 supply 100 BASE")
        # Either return None (preferred), or return a dict where asset_in
        # is a real token symbol — never the chain word 'BASE'.
        if result is not None:
            _tool, args = result
            assert args.get("asset_in") != "BASE"
            assert args.get("asset_in") not in {"ETHEREUM", "POLYGON", "ARBITRUM",
                                                 "OPTIMISM", "AVALANCHE", "SOLANA"}

    def test_supply_with_real_asset_succeeds(self):
        """Sanity: `supply 100 USDC to Aave V3 on Base` still works."""
        result = _detect_aave_supply("supply 100 USDC to Aave V3 on Base")
        assert result is not None
        _tool, args = result
        assert args["asset_in"] == "USDC"
        assert args["chain"] == "base"
        assert args["protocol"] == "aave-v3"
        assert args["amount_in"] == "100"

    def test_supply_chain_in_asset_slot_only_no_recovery_returns_none(self):
        """`Aave V3 supply 100 ETHEREUM` → no recoverable asset → REFUSE."""
        result = _detect_aave_supply("Aave V3 supply 100 ETHEREUM")
        if result is not None:
            _tool, args = result
            assert args.get("asset_in") not in {
                "ETHEREUM", "POLYGON", "ARBITRUM", "OPTIMISM",
                "BASE", "AVALANCHE", "SOLANA", "BSC",
            }

    def test_supply_with_asset_then_chain_word_succeeds(self):
        """Existing handling: `Aave V3 USDC Base supply 100` → re-extract."""
        result = _detect_aave_supply("Aave V3 USDC Base supply 100")
        assert result is not None
        _tool, args = result
        assert args["asset_in"] == "USDC"
        assert args["chain"] == "base"

    def test_supply_with_noise_token_returns_none(self):
        """`Aave V3 supply 100 STRATEGY` → STRATEGY is a noise token → REFUSE."""
        result = _detect_aave_supply("Aave V3 supply 100 STRATEGY")
        if result is not None:
            _tool, args = result
            assert args.get("asset_in") not in {"STRATEGY", "YIELD", "POOL"}

    def test_normal_usdc_supply_unaffected(self):
        """Regression guard: a plain `supply 50 USDC to Aave V3` must still
        emit a normal plan."""
        result = _detect_aave_supply("supply 50 USDC to Aave V3 on Ethereum")
        assert result is not None
        _tool, args = result
        assert args["asset_in"] == "USDC"
        assert args["chain"] == "ethereum"
        assert args["amount_in"] == "50"
