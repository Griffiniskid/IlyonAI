from __future__ import annotations

import math

from src.defi.search.models import (
    ExcludedOpportunity,
    OpportunityCandidate,
    OpportunitySearchRequest,
    OpportunitySearchResult,
)


def _candidate_exclusions(candidate: OpportunityCandidate, request: OpportunitySearchRequest) -> list[str]:
    reasons: list[str] = []
    if request.chains and candidate.chain.lower() not in request.chains:
        reasons.append("chain_not_requested")
    if request.product_types and candidate.product_type.lower() not in request.product_types:
        reasons.append("product_type_not_requested")
    if request.asset_hint and request.asset_hint.upper() not in _symbol_assets(candidate.symbol):
        reasons.append("asset_mismatch")
    if request.risk_levels and candidate.risk_level.upper() not in request.risk_levels:
        reasons.append("risk_not_requested")
    apy = float(candidate.apy or 0.0)
    if request.min_apy is not None and apy < request.min_apy:
        reasons.append("apy_below_target_band")
    if request.max_apy is not None and apy > request.max_apy:
        reasons.append("apy_above_target_band")
    tvl = float(candidate.tvl_usd or 0.0)
    if tvl < request.min_tvl:
        reasons.append("tvl_below_discovery_floor")
    if not request.include_experimental and apy > 500.0:
        reasons.append("apy_outlier_without_experimental_opt_in")
    return reasons


def _symbol_assets(symbol: str) -> set[str]:
    return {part.upper() for part in re_split_symbol(symbol) if part}


def re_split_symbol(symbol: str) -> list[str]:
    return [part for part in symbol.replace("/", "-").replace("_", "-").split("-") if part]


def _target_fit(candidate: OpportunityCandidate, request: OpportunitySearchRequest) -> float:
    if request.target_apy is None:
        return 0.0
    apy = float(candidate.apy or 0.0)
    distance = abs(apy - request.target_apy)
    return max(0.0, 1.0 - (distance / max(request.target_apy, 1.0)))


def _sentinel_score(candidate: OpportunityCandidate) -> float:
    summary = candidate.sentinel_summary or {}
    score = summary.get("opportunity_score") or summary.get("overall_score") or summary.get("sentinel")
    try:
        return float(score)
    except (TypeError, ValueError):
        return 50.0


def _liquidity_score(candidate: OpportunityCandidate) -> float:
    tvl = float(candidate.tvl_usd or 0.0)
    return math.log10(max(tvl, 1.0))


def _ranking_score(candidate: OpportunityCandidate, request: OpportunitySearchRequest) -> float:
    apy = float(candidate.apy or 0.0)
    objective = request.ranking_objective
    if objective == "highest_sentinel_score":
        return (_sentinel_score(candidate) * 10.0) + min(apy, 120.0)
    if objective == "highest_apy_after_sanity_filters":
        return apy + (_sentinel_score(candidate) * 0.1)
    if objective == "target_apy_fit":
        return (_target_fit(candidate, request) * 1_000.0) + _liquidity_score(candidate)
    if objective == "execution_ready_strategy":
        return (1_000.0 if candidate.executable else 0.0) + (_target_fit(candidate, request) * 100.0) + _sentinel_score(candidate)
    return (_target_fit(candidate, request) * 500.0) + (_sentinel_score(candidate) * 2.0) + _liquidity_score(candidate)


def rank_opportunities(
    candidates: list[OpportunityCandidate],
    request: OpportunitySearchRequest,
) -> OpportunitySearchResult:
    primary: list[OpportunityCandidate] = []
    excluded: list[ExcludedOpportunity] = []
    for candidate in candidates:
        reasons = _candidate_exclusions(candidate, request)
        if reasons:
            excluded.append(ExcludedOpportunity(candidate=candidate, reason_codes=reasons))
        else:
            primary.append(candidate)

    primary.sort(key=lambda candidate: _ranking_score(candidate, request), reverse=True)
    limited = primary[: max(1, int(request.limit or 8))]
    return OpportunitySearchResult(primary=limited, excluded=excluded)
