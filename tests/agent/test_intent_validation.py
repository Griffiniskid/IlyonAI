"""Unit tests for src/agent/intent/validation.py."""
from __future__ import annotations

import pytest

from src.agent.intent.validation import (
    STOP_WORDS,
    filter_symbol_candidates,
    is_cross_chain,
    is_stop_word,
    is_valid_symbol_shape,
    parse_amount_base_units,
    parse_amount_human,
    token_supported_on_chain,
    translate_aggregator_error,
    validate_quote_output,
    validate_swap_params,
)


@pytest.mark.parametrize("word", [
    "WALLET", "FROM", "MY", "TO", "ETHEREUM", "SOLANA", "CHAIN",
    "PORTFOLIO", "HOLDINGS", "BAGS", "STASH", "ASSETS",
])
def test_stop_words_block(word):
    assert is_stop_word(word)
    assert is_stop_word(word.lower())


@pytest.mark.parametrize("token", ["SOL", "USDC", "WETH", "BONK", "FATPENGU"])
def test_real_tokens_pass_shape(token):
    assert is_valid_symbol_shape(token)
    assert not is_stop_word(token)


def test_filter_symbol_candidates_drops_noise():
    raw = ["swap", "100", "USDC", "on", "solana", "chain", "from", "my", "wallet", "to", "WBNB"]
    out = filter_symbol_candidates(raw)
    assert "USDC" in out
    assert "WBNB" in out
    assert "WALLET" not in out
    assert "CHAIN" not in out
    assert "SOLANA" not in out
    # And preserves first-seen order, deduped
    assert out == ["USDC", "WBNB"]


def test_token_supported_on_chain():
    assert token_supported_on_chain("SOL", 101) is True
    assert token_supported_on_chain("SOL", 1) is False
    assert token_supported_on_chain("WETH", 1) is True
    assert token_supported_on_chain("WETH", 101) is False
    assert token_supported_on_chain("ZOOMER", 101) is None  # unknown
    assert token_supported_on_chain("USDC", 56) is True


def test_is_cross_chain_detects_sol_to_weth():
    # SOL is Solana-native, WETH is EVM — on chain 101 this is cross-chain
    assert is_cross_chain("SOL", "WETH", 101) is True
    # Same set: WETH on Ethereum (chain 1) — cross-chain because SOL not on 1
    assert is_cross_chain("SOL", "WETH", 1) is True


def test_is_cross_chain_allows_same_chain():
    assert is_cross_chain("USDC", "WETH", 1) is False
    assert is_cross_chain("SOL", "USDC", 101) is False
    assert is_cross_chain("BNB", "CAKE", 56) is False


def test_validate_swap_rejects_stopword_tokens():
    v = validate_swap_params(token_in="WALLET", token_out="WBNB", chain_id=56, amount_in="100")
    assert not v.ok
    assert v.error_code == "invalid_token_in"


def test_validate_swap_rejects_same_token():
    v = validate_swap_params(token_in="USDC", token_out="USDC", chain_id=1, amount_in="100")
    assert not v.ok
    assert v.error_code == "same_token"


def test_validate_swap_rejects_zero_amount():
    v = validate_swap_params(token_in="SOL", token_out="USDC", chain_id=101, amount_in="0")
    assert not v.ok
    assert v.error_code == "invalid_amount"


def test_validate_swap_routes_cross_chain():
    v = validate_swap_params(token_in="SOL", token_out="WETH", chain_id=101, amount_in="100000000")
    assert not v.ok
    assert v.error_code == "cross_chain"
    assert v.suggested_action == "bridge"


def test_validate_swap_accepts_valid():
    v = validate_swap_params(token_in="SOL", token_out="USDC", chain_id=101, amount_in="100000000")
    assert v.ok


def test_validate_swap_accepts_sentinel_amount():
    v = validate_swap_params(
        token_in="SOL", token_out="USDC", chain_id=101,
        amount_in="ALL", amount_is_sentinel=True,
    )
    assert v.ok


def test_validate_swap_rejects_token_not_on_chain():
    v = validate_swap_params(token_in="WETH", token_out="USDC", chain_id=101, amount_in="1000000")
    assert not v.ok
    assert v.error_code in ("cross_chain", "token_not_on_chain")


def test_translate_aggregator_from_address_invalid():
    msg = translate_aggregator_error(
        'Enso API 400: {"message":"fromAddress is not a valid address (guest).","error":"Bad Request"}'
    )
    assert "wallet" in msg.lower()
    assert "guest" not in msg.lower()  # raw token scrubbed


def test_translate_aggregator_jupiter_wrongsize():
    msg = translate_aggregator_error("Jupiter quote error 400: outputMint cannot be parsed: WrongSize")
    assert "bridge" in msg.lower() or "valid solana mint" in msg.lower()
    assert "WrongSize" not in msg  # raw error scrubbed


def test_translate_aggregator_enso_429():
    msg = translate_aggregator_error("Enso API 429: You've exceeded the request limit of 1rps")
    assert "rate-limit" in msg.lower() or "rate limit" in msg.lower() or "rps" not in msg.lower()


def test_translate_aggregator_rate_limit_generic():
    msg = translate_aggregator_error("exceeded the request limit")
    assert "rate" in msg.lower()


def test_validate_quote_output_rejects_zero():
    v = validate_quote_output(amount_in_human=100, amount_out_human=0)
    assert not v.ok
    assert v.error_code == "zero_amount_out"


def test_validate_quote_output_rejects_negative():
    v = validate_quote_output(amount_in_human=100, amount_out_human="-0.000001")
    assert not v.ok


def test_validate_quote_output_accepts_positive():
    v = validate_quote_output(amount_in_human=100, amount_out_human="0.001")
    assert v.ok


def test_parse_amount_human():
    assert parse_amount_human("100") is not None
    assert parse_amount_human("0.001") is not None
    assert parse_amount_human("0") is None
    assert parse_amount_human("-1") is None
    assert parse_amount_human("garbage") is None
    assert parse_amount_human(None) is None
    assert parse_amount_human("999999999999999999999") is None  # ceiling


def test_parse_amount_base_units():
    assert parse_amount_base_units("100000000") == 100_000_000
    assert parse_amount_base_units("0") is None
    assert parse_amount_base_units("ALL") is None
    assert parse_amount_base_units("1.5") is None  # decimals not allowed in base units
    assert parse_amount_base_units(None) is None
