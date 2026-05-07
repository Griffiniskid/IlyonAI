"""Regression tests for the intent detectors that route signable actions.

These cover the bug class the tester reported in the screenshots:
  - 'swap all FATPENGU from my wallet to usdc' previously crashed with
    `simulate_swap amount Field required, token_in='WALLET'`
  - 'minimum risk' wasn't parsed → 5x HIGH-risk pools returned
  - bare 'stake 0.1 bnb' / 'stake all my SOL' returned empty defi search
  - bridge 'all' lacked a deterministic detector
  - send/transfer 'all' lacked a deterministic detector

Each detector returns ('tool_name', params) or None. The runtime tuple at
the bottom of simple_runtime.py iterates them in order.
"""
from __future__ import annotations

import pytest

from src.agent.simple_runtime import (
    _detect_bridge_signable,
    _detect_stake_all,
    _detect_stake_simple,
    _detect_swap_signable,
    _detect_transfer_plan,
    _quantifier_to_amount,
)
from src.agent.intent.defi_intent import parse_defi_intent


# ── swap-all noise-word filter ──────────────────────────────────────────────
class TestSwapAllNoiseFilter:
    def test_does_not_capture_wallet_as_symbol(self):
        # The exact tester message that originally produced
        # `simulate_swap amount Field required, token_in='WALLET'`.
        result = _detect_swap_signable("swap all FATPENGU from my wallet to usdc")
        assert result is not None
        tool, args = result
        assert tool == "build_swap_tx"
        assert args["token_in"] == "FATPENGU"
        assert args["token_out"] == "USDC"
        assert args["amount_in"] == "ALL"
        assert args["chain_id"] == 101  # unknown ticker → Solana default

    def test_swap_all_with_in_my_wallet_clause(self):
        result = _detect_swap_signable("swap all SOL in my wallet to USDC")
        assert result and result[1]["token_in"] == "SOL"
        assert result[1]["amount_in"] == "ALL"

    @pytest.mark.parametrize("text", [
        "swap all wallet to USDC",
        "swap max my to USDC",
        "swap entire from to USDC",
    ])
    def test_noise_words_rejected(self, text):
        # WALLET / MY / FROM in the symbol position must short-circuit so the
        # message can fall through to the LLM (which knows it's malformed).
        assert _detect_swap_signable(text) is None


# ── swap fractional amounts ─────────────────────────────────────────────────
class TestSwapFractional:
    @pytest.mark.parametrize("phrase,expected", [
        ("swap half my SOL to USDC", "PCT:50"),
        ("swap 50% SOL to USDC", "PCT:50"),
        ("swap 25% of my SOL to USDC", "PCT:25"),
        ("swap 75% SOL to USDC", "PCT:75"),
        ("swap 10% SOL to USDC", "PCT:10"),
        ("swap quarter of my SOL to USDC", "PCT:25"),
        ("swap all SOL to USDC", "ALL"),
        ("swap max SOL to USDC", "ALL"),
        ("swap entire SOL to USDC", "ALL"),
    ])
    def test_quantifier_emits_correct_sentinel(self, phrase, expected):
        result = _detect_swap_signable(phrase)
        assert result and result[1]["amount_in"] == expected


# ── sell without explicit destination ───────────────────────────────────────
class TestSellWithoutDestination:
    @pytest.mark.parametrize("phrase,expected_tin,expected_chain", [
        ("sell 100 SHIB", "SHIB", 1),
        ("sell all SHIB", "SHIB", 1),
        ("dump 0.5 BONK", "BONK", 101),
        ("sell all BNB", "BNB", 56),
        ("sell all FATPENGU", "FATPENGU", 101),
        ("sell half my BNB", "BNB", 56),
        ("sell 25% of my SHIB", "SHIB", 1),
        ("dump all PEPE", "PEPE", 1),
    ])
    def test_destination_defaults_usdc_with_correct_chain(self, phrase, expected_tin, expected_chain):
        result = _detect_swap_signable(phrase)
        assert result is not None, f"detector should match: {phrase!r}"
        _, args = result
        assert args["token_in"] == expected_tin
        assert args["token_out"] == "USDC"
        assert args["chain_id"] == expected_chain


# ── stake intents ───────────────────────────────────────────────────────────
class TestStakeIntents:
    def test_bare_stake_routes_to_lst(self):
        # 'stake 0.1 bnb' → swap into slisBNB on BSC
        result = _detect_stake_simple("stake 0.1 bnb")
        assert result and result[0] == "build_swap_tx"
        args = result[1]
        assert args["chain_id"] == 56
        assert args["token_in"] == "BNB"
        # slisBNB address — case-insensitive comparison
        assert args["token_out"].lower() == "0xb0b84d294e0c75a6abe60171b70edeb2efd14a1b"
        assert args["amount_in"] == str(10**17)  # 0.1 * 1e18

    def test_stake_with_protocol_qualifier_yields_to_compose_plan(self):
        # 'stake 1 eth on lido' must NOT be routed to the simple LST swap;
        # the plan-based detector handles protocol-qualified stakes.
        assert _detect_stake_simple("stake 1 eth on lido") is None

    def test_stake_all_my_sol_uses_jitosol(self):
        result = _detect_stake_all("stake all my SOL")
        assert result and result[0] == "build_swap_tx"
        args = result[1]
        assert args["chain_id"] == 101
        assert args["token_in"] == "SOL"
        # jitoSOL mint
        assert args["token_out"].lower() == "j1toso1uck3rlmjorhttrvwy9hj7x8v9yyac6y7kgcpn"
        assert args["amount_in"] == "ALL"

    def test_stake_all_idle_defers_to_plan(self):
        # Existing _detect_stake_amount_plan handles 'stake all my idle X'.
        assert _detect_stake_all("stake all my idle ETH") is None


# ── bridge detector ─────────────────────────────────────────────────────────
class TestBridgeDetector:
    def test_numeric_bridge(self):
        result = _detect_bridge_signable("bridge 1 SOL from solana to ethereum")
        assert result and result[0] == "build_bridge_tx"
        args = result[1]
        assert args["src_chain_id"] == 7565164  # deBridge Solana enum
        assert args["dst_chain_id"] == 1
        assert args["token_in"] == "SOL"
        assert args["amount"] == str(10**9)  # 1 SOL = 1e9 lamports

    def test_bridge_all(self):
        result = _detect_bridge_signable("bridge all SOL from solana to ethereum")
        assert result and result[1]["amount"] == "ALL"

    def test_bsc_usdc_uses_18_decimals(self):
        # BSC USDC is BNB-pegged at 18 decimals, NOT 6. Cross-chain bridges
        # would underfund deBridge by 12 orders of magnitude with 6.
        result = _detect_bridge_signable("bridge 0.5 USDC from bsc to base")
        assert result and result[1]["amount"] == str(int(0.5 * 10**18))

    def test_same_chain_rejected(self):
        # No cross-chain hop → not a bridge.
        assert _detect_bridge_signable("bridge 1 SOL from solana to solana") is None


# ── transfer detector ───────────────────────────────────────────────────────
class TestTransferDetector:
    def test_numeric_transfer(self):
        result = _detect_transfer_plan("send 5 USDC to 0xabc")
        assert result and result[0] == "compose_plan"
        step = result[1]["steps"][0]
        assert step["params"]["token"] == "USDC"
        assert step["params"]["amount"] == str(5 * 10**6)

    def test_transfer_all(self):
        result = _detect_transfer_plan("send all FATPENGU from my wallet to 5dQ8")
        assert result and result[0] == "compose_plan"
        step = result[1]["steps"][0]
        assert step["params"]["token"] == "FATPENGU"
        assert step["params"]["amount"] == "ALL"

    def test_send_all_wallet_noise_rejected(self):
        # Can't capture 'wallet' as the token symbol.
        assert _detect_transfer_plan("send all wallet to 0xabc") is None


# ── defi risk-level parser ──────────────────────────────────────────────────
class TestDefiRiskParser:
    @pytest.mark.parametrize("phrase,expected", [
        ("give me a liquidity pool with highest apr but with minimum risk", ["LOW"]),
        ("show me safest pools", ["LOW"]),
        ("conservative yields please", ["LOW"]),
        ("aggressive high APR pools", ["HIGH"]),
        ("medium risk only", ["MEDIUM"]),
        ("medium and high risk pools", ["MEDIUM", "HIGH"]),
    ])
    def test_phrase_to_risk_levels(self, phrase, expected):
        result = parse_defi_intent(phrase)
        assert result.risk_levels == expected


# ── fractional propagation across bridge/transfer/stake ─────────────────────
class TestFractionalPropagation:
    @pytest.mark.parametrize("phrase,expected", [
        ("bridge half SOL from solana to ethereum", "PCT:50"),
        ("bridge 25% USDC from bsc to base", "PCT:25"),
        ("bridge all SOL from solana to ethereum", "ALL"),
    ])
    def test_bridge_fractional(self, phrase, expected):
        result = _detect_bridge_signable(phrase)
        assert result and result[1]["amount"] == expected

    @pytest.mark.parametrize("phrase,expected", [
        ("send half my USDC to 0xabc", "PCT:50"),
        ("transfer 25% USDC to 0xabc", "PCT:25"),
        ("send all USDC to 0xabc", "ALL"),
    ])
    def test_transfer_fractional(self, phrase, expected):
        result = _detect_transfer_plan(phrase)
        assert result and result[1]["steps"][0]["params"]["amount"] == expected

    @pytest.mark.parametrize("phrase,expected", [
        ("stake half my SOL", "PCT:50"),
        ("stake 25% BNB", "PCT:25"),
        ("stake all my SOL", "ALL"),
    ])
    def test_stake_fractional(self, phrase, expected):
        result = _detect_stake_all(phrase)
        assert result and result[1]["amount_in"] == expected


# ── quantifier mapping (helper sanity) ──────────────────────────────────────
class TestQuantifierMapping:
    @pytest.mark.parametrize("phrase,expected", [
        ("all", "ALL"), ("max", "ALL"), ("100%", "ALL"),
        ("half", "PCT:50"), ("50%", "PCT:50"),
        ("quarter", "PCT:25"), ("25%", "PCT:25"),
        ("75%", "PCT:75"), ("10%", "PCT:10"),
    ])
    def test_quantifier_to_amount(self, phrase, expected):
        assert _quantifier_to_amount(phrase) == expected
