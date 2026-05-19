"""Pin tests for cross-chain intent inference (Pass A rows 10-11).

Bugs caught:

* E01/E02/E07 — cross-chain prompt with post-action emitted pool_link.
* E04/E05/E06/E09/E12/E13/E14 — cross-chain prompt with destination only
  silently dropped the source chain.

These tests pin the contract that `infer_cross_chain_hint`:

1. Recognises a cross-chain verb + destination chain.
2. Flags `has_post_action=True` whenever a yield verb follows (`then supply`,
   `and stake`, …) so the routing layer can force composed_plan.
3. Returns `source_ambiguous=True` instead of guessing — the routing layer is
   then responsible for emitting CROSS_CHAIN_SOURCE_AMBIGUOUS.
4. Resolves the source from "from <chain>" or token home-chain.
"""
from __future__ import annotations

import pytest

from src.agent.cross_chain import (
    CrossChainIntent,
    cross_chain_source_blocker_payload,
    infer_cross_chain_hint,
)


class TestPlainProse:
    def test_non_cross_chain_message_returns_falsey(self):
        intent = infer_cross_chain_hint("what is the apy on aave usdc?")
        assert intent.is_cross_chain is False
        assert intent.has_post_action is False
        assert intent.source_chain is None
        assert intent.dest_chain is None

    def test_empty_message_returns_falsey(self):
        intent = infer_cross_chain_hint("")
        assert intent.is_cross_chain is False
        assert intent.needs_composed_plan is False
        assert intent.needs_source_blocker is False


class TestExplicitFromTo:
    def test_bridge_with_post_action_must_use_composed_plan(self):
        # E01 / E02 / E07 pin
        intent = infer_cross_chain_hint(
            "bridge 100 USDC from Arbitrum to Base then supply on Aave V3"
        )
        assert intent.is_cross_chain is True
        assert intent.has_post_action is True
        assert intent.source_chain == "arbitrum"
        assert intent.dest_chain == "base"
        assert intent.source_ambiguous is False
        assert intent.needs_composed_plan is True
        assert intent.needs_source_blocker is False

    def test_move_from_polygon_to_mainnet_aave(self):
        intent = infer_cross_chain_hint(
            "move my USDC from polygon to mainnet aave"
        )
        assert intent.is_cross_chain is True
        assert intent.source_chain == "polygon"
        assert intent.dest_chain == "ethereum"
        assert intent.source_ambiguous is False

    def test_bridge_no_post_action(self):
        # "bridge from X to Y" alone — cross-chain but no composed plan needed.
        intent = infer_cross_chain_hint("bridge USDC from Arbitrum to Optimism")
        assert intent.is_cross_chain is True
        assert intent.has_post_action is False
        assert intent.needs_composed_plan is False

    def test_l1_alias_resolves_to_ethereum(self):
        intent = infer_cross_chain_hint(
            "bridge 50 USDT from optimism to L1 then stake on Lido"
        )
        assert intent.source_chain == "optimism"
        assert intent.dest_chain == "ethereum"


class TestSourceAmbiguous:
    def test_dest_only_usdc_triggers_blocker(self):
        # E04 / E05 / E06 / E09 / E12 / E13 / E14 pin.
        # USDC has no unambiguous home chain so the source MUST be flagged.
        intent = infer_cross_chain_hint(
            "bridge my USDC to mainnet and supply on Aave"
        )
        assert intent.is_cross_chain is True
        assert intent.source_chain is None
        assert intent.dest_chain == "ethereum"
        assert intent.source_ambiguous is True
        assert intent.needs_source_blocker is True

    def test_dest_only_no_token_triggers_blocker(self):
        intent = infer_cross_chain_hint("bridge to base then supply on aave")
        assert intent.is_cross_chain is True
        assert intent.source_ambiguous is True
        assert intent.needs_source_blocker is True

    def test_token_home_chain_resolves_source_when_implicit(self):
        # SOL is unambiguously Solana-native — infer source.
        intent = infer_cross_chain_hint("bridge 1 SOL to ethereum and stake")
        assert intent.is_cross_chain is True
        assert intent.source_chain == "solana"
        assert intent.dest_chain == "ethereum"
        assert intent.source_ambiguous is False

    def test_bnb_native_token_resolves_source(self):
        intent = infer_cross_chain_hint(
            "move my BNB to ethereum then supply on aave"
        )
        assert intent.source_chain == "bsc"
        assert intent.dest_chain == "ethereum"
        assert intent.source_ambiguous is False

    def test_blocker_payload_shape(self):
        payload = cross_chain_source_blocker_payload(
            dest_chain="base", message="bridge usdc to base"
        )
        assert payload["code"] == "CROSS_CHAIN_SOURCE_AMBIGUOUS"
        assert payload["severity"] == "blocker"
        assert payload["title"] == "Source chain missing"
        assert "base" in payload["detail"]
        # cta nudges the user to specify the source chain explicitly
        assert "source" in payload["cta"].lower()


class TestPostActionVariants:
    @pytest.mark.parametrize(
        "phrase",
        [
            "bridge USDC from arbitrum to base then supply on aave",
            "bridge USDC from arbitrum to base and stake on lido",
            "bridge USDC from arbitrum to base to deposit into compound",
            "bridge USDC from arbitrum to base, lend on aave",
        ],
    )
    def test_post_action_verbs(self, phrase: str):
        intent = infer_cross_chain_hint(phrase)
        assert intent.is_cross_chain is True
        assert intent.has_post_action is True
        assert intent.needs_composed_plan is True


class TestNonCrossChainGuards:
    def test_swap_does_not_count_as_cross_chain(self):
        intent = infer_cross_chain_hint("swap 100 USDC to WETH on arbitrum")
        # "swap" is not a bridge verb — must not trigger cross-chain branch
        assert intent.is_cross_chain is False

    def test_unknown_destination_not_cross_chain(self):
        # "to mars" — destination doesn't resolve to a known chain slug, so
        # the cross-chain branch must NOT fire (lets existing detectors run).
        intent = infer_cross_chain_hint("bridge USDC to mars then supply")
        assert intent.is_cross_chain is False


class TestSameChainGuard:
    def test_from_to_same_chain_not_cross_chain(self):
        # "from arbitrum to arbitrum" — degenerate, not a real cross-chain.
        intent = infer_cross_chain_hint(
            "bridge USDC from arbitrum to arbitrum then supply"
        )
        # Loose regex still picks "to arbitrum" but the explicit-from path
        # rejects same-chain. Falls through to token-inference, which has
        # no ARB→other inference, so source is ambiguous.
        # Either source_ambiguous OR source!=dest is acceptable; the key
        # contract is: we never emit src==dst.
        if intent.source_chain is not None:
            assert intent.source_chain != intent.dest_chain
