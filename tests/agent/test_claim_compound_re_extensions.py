"""V7-071 — claim-and-compound token-first phrasing pin tests.

Pins three forms:
  1. Existing 'Claim my Aave rewards and re-stake into stkAAVE' (regression).
  2. Slipstream/Aerodrome: 'claim AERO and re-stake' (token-first).
  3. Compound V3: 'claim COMP and compound' (token-first).
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import _detect_claim_compound


class TestExistingProtoFirstUnchanged:
    """Regression guard — 'Claim my Aave rewards and re-stake into stkAAVE'
    must still produce the V3 claim-compound plan with reward_token=AAVE."""

    def test_aave_proto_first_still_matches(self):
        result = _detect_claim_compound(
            "Claim my Aave rewards and re-stake into stkAAVE"
        )
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["protocol"] == "aave-v3"
        assert args["action"] == "claim_compound"
        assert args["asset_in"] == "AAVE"
        assert args["extra"]["reward_token"] == "AAVE"
        assert args["extra"]["stake_target"] == "stkaave"


class TestSlipstreamAerodromeTokenFirst:
    """V7-071 — Slipstream/Aerodrome 'claim AERO and re-stake'."""

    @pytest.mark.parametrize("msg,verb_normalised", [
        ("claim AERO and re-stake",         "restake"),
        ("Claim AERO and restake",          "restake"),
        ("claim AERO and compound",         "compound"),
        ("Claim my AERO and re-stake",      "restake"),
        ("claim the AERO and stake back",   "stakeback"),
    ])
    def test_aero_variants(self, msg, verb_normalised):
        result = _detect_claim_compound(msg)
        assert result is not None, f"V7-071 — must match: {msg!r}"
        _, args = result
        assert args["protocol"] == "aerodrome"
        assert args["asset_in"] == "AERO"
        assert args["extra"]["claim_compound"] is True
        assert args["extra"]["reward_token"] == "AERO"
        assert args["extra"]["stake_target"] == "aerodrome-veaero"
        assert args["extra"]["verb"] == verb_normalised


class TestCompoundV3TokenFirst:
    """V7-071 — Compound V3 'claim COMP and compound'."""

    @pytest.mark.parametrize("msg", [
        "claim COMP and compound",
        "Claim COMP and re-stake",
        "Claim my COMP and reinvest",
    ])
    def test_comp_variants(self, msg):
        result = _detect_claim_compound(msg)
        assert result is not None, f"V7-071 — must match: {msg!r}"
        _, args = result
        assert args["protocol"] == "compound-v3"
        assert args["asset_in"] == "COMP"
        assert args["extra"]["reward_token"] == "COMP"
        assert args["extra"]["stake_target"] == "compound-staking"


class TestOtherWhitelistedTokens:
    """V7-071 — sanity check on the broader _CLAIM_TOKEN_TO_PROTO table."""

    @pytest.mark.parametrize("token,proto", [
        ("VELO",   "velodrome"),
        ("CRV",    "curve"),
        ("CVX",    "convex"),
        ("BAL",    "balancer-v2"),
        ("PENDLE", "pendle"),
    ])
    def test_token_first_whitelisted(self, token, proto):
        msg = f"claim {token} and compound"
        result = _detect_claim_compound(msg)
        assert result is not None, f"V7-071 — must match: {msg!r}"
        _, args = result
        assert args["protocol"] == proto
        assert args["asset_in"] == token


class TestUnknownTokenRejected:
    """Conservative: random tickers must not false-match."""

    @pytest.mark.parametrize("msg", [
        "claim USDC and compound",     # not a reward token
        "claim FAKE and re-stake",     # unknown ticker
        "claim XYZ and reinvest",
    ])
    def test_unknown_token_returns_none(self, msg):
        assert _detect_claim_compound(msg) is None


class TestChainOverrideOnTokenFirst:
    def test_chain_after_token_form(self):
        result = _detect_claim_compound(
            "claim AERO and re-stake on base"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "base"
        assert args["protocol"] == "aerodrome"
