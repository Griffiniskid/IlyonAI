"""Sanity-penalty tests for `rank_opportunities`.

Pin the search-ranking gap fix: thin-TVL high-APY pools must NOT outrank
deep-TVL reasonable-APY pools when the caller has not opted into
experimental opportunities.
"""
from __future__ import annotations

from src.defi.search.models import OpportunityCandidate, OpportunitySearchRequest
from src.defi.search.ranking import rank_opportunities


def _candidate(
    *,
    protocol: str,
    apy: float,
    tvl_usd: float,
    symbol: str = "USDC",
    risk_level: str = "MODERATE",
    chain: str = "ethereum",
) -> OpportunityCandidate:
    return OpportunityCandidate(
        protocol=protocol,
        chain=chain,
        symbol=symbol,
        apy=apy,
        tvl_usd=tvl_usd,
        risk_level=risk_level,
        sentinel_summary={"opportunity_score": 70},
    )


def test_include_experimental_default_false() -> None:
    """Bare `OpportunitySearchRequest()` must default to safe mode."""
    request = OpportunitySearchRequest()
    assert request.include_experimental is False


def test_high_apy_thin_tvl_demoted_when_experimental_false() -> None:
    """MAXUSD-style 1330% APY $81k TVL pool must rank AFTER a 4% APY $50M
    TVL pool when the caller has not opted into experimental opps.

    Note: candidates with apy > 1000 are filtered out entirely by
    `_candidate_exclusions` (apy_outlier_without_experimental_opt_in). The
    sanity penalty handles the 99-1000% band that the exclusion misses, so
    we use 250% APY here to exercise the penalty path directly.
    """
    thin_high = _candidate(protocol="MAXUSD", apy=250.0, tvl_usd=81_000.0)
    deep_low = _candidate(protocol="DeepStable", apy=4.0, tvl_usd=50_000_000.0)
    request = OpportunitySearchRequest(
        ranking_objective="highest_apy_after_sanity_filters",
        include_experimental=False,
    )
    result = rank_opportunities([thin_high, deep_low], request)
    protocols = [c.protocol for c in result.primary]
    assert protocols == ["DeepStable", "MAXUSD"], (
        f"thin-TVL high-APY pool must be demoted; got order {protocols}"
    )


def test_high_apy_thin_tvl_kept_when_experimental_true() -> None:
    """With `include_experimental=True`, the scorer's natural order wins —
    high APY first.
    """
    thin_high = _candidate(protocol="MAXUSD", apy=250.0, tvl_usd=81_000.0)
    deep_low = _candidate(protocol="DeepStable", apy=4.0, tvl_usd=50_000_000.0)
    request = OpportunitySearchRequest(
        ranking_objective="highest_apy_after_sanity_filters",
        include_experimental=True,
    )
    result = rank_opportunities([thin_high, deep_low], request)
    protocols = [c.protocol for c in result.primary]
    assert protocols == ["MAXUSD", "DeepStable"], (
        f"experimental opt-in must preserve high-APY first; got {protocols}"
    )


def test_low_apy_thin_tvl_kept() -> None:
    """Only the high-APY + thin-TVL COMBO is demoted. A 4% APY $500k TVL
    pool (below the $1M TVL floor but with a sane APY) must NOT be demoted.
    """
    thin_low = _candidate(protocol="SmallPool", apy=4.0, tvl_usd=500_000.0)
    deep_low = _candidate(protocol="DeepStable", apy=3.0, tvl_usd=50_000_000.0)
    request = OpportunitySearchRequest(
        ranking_objective="highest_apy_after_sanity_filters",
        include_experimental=False,
        min_tvl=0.0,  # bypass the discovery floor exclusion
    )
    result = rank_opportunities([thin_low, deep_low], request)
    protocols = [c.protocol for c in result.primary]
    # SmallPool has higher APY (4.0 vs 3.0) and is NOT demoted, so it ranks first.
    assert protocols == ["SmallPool", "DeepStable"], (
        f"low-APY thin-TVL pool must NOT be demoted; got {protocols}"
    )


def test_high_apy_deep_tvl_kept() -> None:
    """Only the high-APY + thin-TVL COMBO is demoted. A 200% APY pool with
    $50M TVL satisfies the TVL floor and must NOT be demoted.
    """
    deep_high = _candidate(protocol="LegitFarm", apy=200.0, tvl_usd=50_000_000.0)
    deep_low = _candidate(protocol="DeepStable", apy=4.0, tvl_usd=50_000_000.0)
    request = OpportunitySearchRequest(
        ranking_objective="highest_apy_after_sanity_filters",
        include_experimental=False,
    )
    result = rank_opportunities([deep_high, deep_low], request)
    protocols = [c.protocol for c in result.primary]
    # LegitFarm has higher APY and deep TVL — sanity penalty must not fire.
    assert protocols == ["LegitFarm", "DeepStable"], (
        f"high-APY deep-TVL pool must NOT be demoted; got {protocols}"
    )
