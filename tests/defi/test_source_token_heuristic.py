"""Pin tests for spec §6d source-token smart-heuristic (path B fallback).

Covers eligibility thresholds (20% APR AND 50% source-token TVL share),
selection ordering (APR -> share -> TVL), empty inputs, and recommendation
card shape.
"""
from __future__ import annotations
from decimal import Decimal

import pytest

from src.defi.strategy.source_token_heuristic import (
    SMART_HEURISTIC_MIN_APR,
    SMART_HEURISTIC_MIN_TOKEN_SHARE,
    SourceTokenCandidate,
    build_redirect_recommendation_card,
    is_smart_heuristic_eligible,
    pick_smart_heuristic_alternative,
)


def _mk(
    apr: str,
    share: str,
    tvl: str = "1000000",
    pool_address: str = "0xpool",
    protocol: str = "curve",
    chain: str = "ethereum",
    pair: tuple[str, str] = ("USDT", "DAI"),
) -> SourceTokenCandidate:
    return SourceTokenCandidate(
        pool_address=pool_address,
        protocol=protocol,
        chain=chain,
        pair_symbols=pair,
        apr_30d=Decimal(apr),
        tvl_usd=Decimal(tvl),
        source_token_share=Decimal(share),
    )


# --- thresholds (constants pin) -------------------------------------------------


def test_thresholds_pinned():
    """§6d thresholds must remain 20% APR + 50% source-token TVL share."""
    assert SMART_HEURISTIC_MIN_APR == Decimal("0.20")
    assert SMART_HEURISTIC_MIN_TOKEN_SHARE == Decimal("0.50")


# --- eligibility ----------------------------------------------------------------


def test_eligible_21pct_apr_60pct_share():
    """21% APR + 60% USDT share -> eligible (B-path)."""
    c = _mk(apr="0.21", share="0.60")
    assert is_smart_heuristic_eligible(c) is True


def test_not_eligible_19pct_apr_60pct_share():
    """19% APR + 60% share -> NOT eligible (APR below 20%)."""
    c = _mk(apr="0.19", share="0.60")
    assert is_smart_heuristic_eligible(c) is False


def test_not_eligible_25pct_apr_49pct_share():
    """25% APR + 49% share -> NOT eligible (share below 50%)."""
    c = _mk(apr="0.25", share="0.49")
    assert is_smart_heuristic_eligible(c) is False


def test_eligible_exact_threshold_boundary():
    """Exact 20% APR + 50% share -> eligible (>= comparison)."""
    c = _mk(apr="0.20", share="0.50")
    assert is_smart_heuristic_eligible(c) is True


def test_not_eligible_both_below():
    """Both APR and share below threshold -> NOT eligible."""
    c = _mk(apr="0.10", share="0.30")
    assert is_smart_heuristic_eligible(c) is False


# --- selection ordering ---------------------------------------------------------


def test_pick_highest_apr_wins():
    """Multiple eligible candidates -> highest APR wins."""
    low = _mk(apr="0.21", share="0.80", pool_address="0xlow")
    high = _mk(apr="0.35", share="0.55", pool_address="0xhigh")
    mid = _mk(apr="0.25", share="0.60", pool_address="0xmid")
    pick = pick_smart_heuristic_alternative("USDT", [low, high, mid])
    assert pick is not None
    assert pick.pool_address == "0xhigh"


def test_pick_tiebreak_on_share_when_apr_equal():
    """APR tie -> larger source_token_share wins."""
    a = _mk(apr="0.25", share="0.55", pool_address="0xa")
    b = _mk(apr="0.25", share="0.75", pool_address="0xb")
    c = _mk(apr="0.25", share="0.60", pool_address="0xc")
    pick = pick_smart_heuristic_alternative("USDT", [a, b, c])
    assert pick is not None
    assert pick.pool_address == "0xb"


def test_pick_tiebreak_on_tvl_when_apr_and_share_equal():
    """APR + share tie -> larger TVL wins."""
    small = _mk(apr="0.25", share="0.60", tvl="500000", pool_address="0xsmall")
    big = _mk(apr="0.25", share="0.60", tvl="9000000", pool_address="0xbig")
    mid = _mk(apr="0.25", share="0.60", tvl="2000000", pool_address="0xmid")
    pick = pick_smart_heuristic_alternative("USDT", [small, big, mid])
    assert pick is not None
    assert pick.pool_address == "0xbig"


def test_pick_skips_ineligible_even_if_higher_apr():
    """A 50% APR candidate with only 40% share must NOT be picked over a 21%/60% one."""
    ineligible_high_apr = _mk(apr="0.50", share="0.40", pool_address="0xskip")
    eligible_low_apr = _mk(apr="0.21", share="0.60", pool_address="0xpick")
    pick = pick_smart_heuristic_alternative("USDT", [ineligible_high_apr, eligible_low_apr])
    assert pick is not None
    assert pick.pool_address == "0xpick"


# --- empty / no-eligible --------------------------------------------------------


def test_pick_empty_list_returns_none():
    """Empty candidate list -> None."""
    assert pick_smart_heuristic_alternative("USDT", []) is None


def test_pick_no_eligible_returns_none():
    """No candidate meets thresholds -> None (fall through to A-path)."""
    candidates = [
        _mk(apr="0.05", share="0.90"),
        _mk(apr="0.50", share="0.10"),
        _mk(apr="0.19", share="0.49"),
    ]
    assert pick_smart_heuristic_alternative("USDT", candidates) is None


# --- recommendation card shape --------------------------------------------------


def test_build_redirect_recommendation_card_shape():
    """Card schema must contain all spec §6d fields with correct types."""
    alt = SourceTokenCandidate(
        pool_address="0xCAFE",
        protocol="curve",
        chain="ethereum",
        pair_symbols=("USDT", "DAI"),
        apr_30d=Decimal("0.245"),
        tvl_usd=Decimal("12500000"),
        source_token_share=Decimal("0.62"),
    )
    card = build_redirect_recommendation_card(
        source_token="USDT",
        original_pool="0xORIG",
        alternative=alt,
    )

    assert card["card_type"] == "source_token_redirect"
    assert card["source_token"] == "USDT"
    assert card["original_pool"] == "0xORIG"

    ap = card["alternative_pool"]
    assert ap["address"] == "0xCAFE"
    assert ap["protocol"] == "curve"
    assert ap["chain"] == "ethereum"
    assert ap["pair"] == "USDT/DAI"
    assert ap["apr_30d"] == "0.245"
    assert ap["tvl_usd"] == "12500000"
    assert ap["source_token_share"] == "0.62"

    # Recommendation text surfaces the converted percentage and protocol.
    assert "24.5%" in card["recommendation"]
    assert "USDT/DAI" in card["recommendation"]
    assert "curve" in card["recommendation"]
    assert "USDT" in card["recommendation"]

    # User choice set must be exactly the three §6d options.
    assert card["user_choice"] == ["use_alternative", "proceed_with_split", "cancel"]


def test_recommendation_card_serializes_decimals_as_strings():
    """Decimal precision is preserved by stringifying — no float coercion."""
    alt = SourceTokenCandidate(
        pool_address="0xDEC",
        protocol="uniswap_v3",
        chain="arbitrum",
        pair_symbols=("USDT", "USDC"),
        apr_30d=Decimal("0.200000001"),
        tvl_usd=Decimal("1234567.89"),
        source_token_share=Decimal("0.500000001"),
    )
    card = build_redirect_recommendation_card("USDT", "0xORIG", alt)
    assert card["alternative_pool"]["apr_30d"] == "0.200000001"
    assert card["alternative_pool"]["tvl_usd"] == "1234567.89"
    assert card["alternative_pool"]["source_token_share"] == "0.500000001"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x", "-q"]))
