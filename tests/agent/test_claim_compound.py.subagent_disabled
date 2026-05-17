"""§7 S12 — claim-and-compound detector pin tests.

'Claim my Aave rewards and re-stake into stkAAVE' must surface as a 2-step
build_yield_execution_plan call: claimRewards on the Incentives Controller,
then stake the AAVE into stkAAVE.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import _detect_claim_compound, detect_intent


class TestAaveClaimRestake:
    def test_basic_claim_restake(self):
        result = _detect_claim_compound(
            "Claim my Aave rewards and re-stake into stkAAVE"
        )
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["protocol"] == "aave-v3"
        assert args["action"] == "claim_compound"
        assert args["asset_in"] == "AAVE"
        assert args["amount_in"] == 0  # claim-all sentinel
        extra = args["extra"]
        assert extra["claim_compound"] is True
        assert extra["reward_token"] == "AAVE"
        assert extra["stake_target"] == "stkaave"

    def test_dispatch_via_detect_intent(self):
        intent = detect_intent(
            "Claim my Aave rewards and re-stake into stkAAVE"
        )
        assert intent is not None
        tool, args = intent
        assert tool == "build_yield_execution_plan"
        assert args["extra"]["claim_compound"] is True


class TestOtherProtocols:
    @pytest.mark.parametrize("proto,expected_slug,reward", [
        ("Compound", "compound-v3", "COMP"),
        ("Curve",    "curve",       "CRV"),
        ("Convex",   "convex",      "CVX"),
        ("Pendle",   "pendle",      "PENDLE"),
        ("Balancer", "balancer-v2", "BAL"),
        ("Aerodrome","aerodrome",   "AERO"),
        ("Velodrome","velodrome",   "VELO"),
        ("GMX",      "gmx",         "GMX"),
        ("Lido",     "lido",        "LDO"),
        ("Morpho",   "morpho-blue", "MORPHO"),
    ])
    def test_named_protocol(self, proto, expected_slug, reward):
        msg = f"Claim my {proto} rewards and compound"
        result = _detect_claim_compound(msg)
        assert result is not None, f"detector failed for {proto}"
        _, args = result
        assert args["protocol"] == expected_slug
        assert args["asset_in"] == reward


class TestVerbForms:
    @pytest.mark.parametrize("verb", [
        "and re-stake",
        "and restake",
        "and compound",
        "and supply back",
        "and reinvest",
        "and stake back",
    ])
    def test_verb_variants(self, verb):
        msg = f"Claim my Aave rewards {verb}"
        result = _detect_claim_compound(msg)
        assert result is not None
        _, args = result
        assert args["extra"]["claim_compound"] is True

    def test_target_override(self):
        result = _detect_claim_compound(
            "Claim my Curve rewards and compound into cvxCRV"
        )
        assert result is not None
        _, args = result
        # User-supplied target wins over default convex.
        assert args["extra"]["stake_target"] == "cvxcrv"


class TestChainOverride:
    def test_bsc_for_pancake(self):
        # Pancakeswap not in CLAIM_COMPOUND map → falls through.
        # Uniswap on bsc is supported by detector via _CLAIM_COMPOUND_PROTOS.
        result = _detect_claim_compound(
            "Claim my Aave rewards and re-stake on arbitrum"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "arbitrum"


class TestMalformedRejected:
    @pytest.mark.parametrize("msg", [
        "Claim rewards",  # no protocol
        "Claim my Aave rewards",  # no verb
        "Stake Aave rewards",  # no claim verb
        "",
        "Claim my Frobnicator rewards and compound",  # unknown protocol
    ])
    def test_malformed_returns_none(self, msg):
        assert _detect_claim_compound(msg) is None
