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
    if request.product_types:
        cand_pt = candidate.product_type.lower()
        if not any(pt.lower() in cand_pt or cand_pt in pt.lower() for pt in request.product_types):
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
    if not request.include_experimental and apy > 1000.0:
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
    # Surface executable pools first: a pool the user can actually one-click
    # deposit into outranks a higher-APY pool they can only stare at. The
    # `executable` flag is set by the search badging pass (cheap capability +
    # static gates) before ranking; the post-rank dry-run then confirms the
    # shown set. Without this boost, high-APY non-executable pools (gmtrade,
    # exotic V3) crowd out the executable ones and the list shows nothing
    # signable.
    exec_bonus = 100_000.0 if getattr(candidate, "executable", False) else 0.0
    # Within the executable tier, prefer pools made of MAJOR tokens. Exotic-token
    # pools (IDAI/YNUSDX/MSUSD…) almost never resolve to a buildable adapter,
    # while major-token pools (USDC/USDT/DAI/WETH/SOL/…) reliably build. This
    # surfaces the pools the dry-run can actually confirm instead of high-APY
    # exotic ones that would only ever get a deep link.
    major_bonus = 50_000.0 if _all_major_tokens(candidate.symbol) else 0.0
    # Surface protocols that RELIABLY build (verified by the execution sweep)
    # above flaky ones (aerodrome/steer/balancer/exotic), so the dry-run gate
    # probes real builders and the EXECUTE button actually appears.
    _slug = (candidate.protocol_slug or candidate.protocol or "").lower()
    reliable_bonus = 200_000.0 if any(_slug.startswith(p) for p in _RELIABLE_EXEC_PROTOCOLS) else 0.0
    return exec_bonus + reliable_bonus + major_bonus + _ranking_score_base(candidate, request)


# Protocol families whose deposits reliably build a signable tx (Enso EVM
# lending/stable-LP/V2-AMM + Solana single-asset LSTs). Derived from the
# pool-execution sweep. Used to rank true builders above flaky pools.
_RELIABLE_EXEC_PROTOCOLS = (
    "aave", "compound", "sky-lending", "sky", "fluid", "curve", "morpho",
    "spark", "ethena", "lido", "rocket-pool", "rocketpool", "ether",
    "pancakeswap", "uniswap-v2",
    "marinade", "jito", "jupiter-staked", "jpool", "blazestake",
)


_MAJOR_TOKENS = frozenset({
    "USDC", "USDT", "DAI", "USDS", "SUSDS", "CRVUSD", "GHO", "FRAX", "USDE",
    "PYUSD", "TUSD", "BUSD", "FDUSD", "USDG", "SUSD", "LUSD", "MIM",
    "WETH", "ETH", "WBTC", "BTC", "CBBTC", "TBTC",
    "SOL", "WSOL", "MSOL", "JITOSOL", "JUPSOL", "BSOL", "BNSOL", "INF",
    "BNB", "WBNB", "AVAX", "WAVAX", "MATIC", "WMATIC", "POL", "ARB", "OP",
    "STETH", "WSTETH", "RETH", "WEETH", "CBETH", "EZETH", "RSETH",
})


def _all_major_tokens(symbol: str | None) -> bool:
    if not symbol:
        return False
    legs = [s.strip().upper() for s in symbol.replace("/", "-").replace("_", "-").split("-") if s.strip()]
    return bool(legs) and all(leg in _MAJOR_TOKENS for leg in legs)


def _ranking_score_base(candidate: OpportunityCandidate, request: OpportunitySearchRequest) -> float:
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


def _apply_sanity_penalty(
    primary: list[OpportunityCandidate],
    request: OpportunitySearchRequest,
) -> list[OpportunityCandidate]:
    """Down-rank pools with high APY (>99%) and thin TVL (<$1M) unless the
    caller has explicitly opted into experimental opportunities. Demoted pools
    are appended to the end of the list while preserving relative order.
    """
    if request.include_experimental:
        return primary
    kept: list[OpportunityCandidate] = []
    demoted: list[OpportunityCandidate] = []
    for candidate in primary:
        apy = float(candidate.apy or 0.0)
        tvl = float(candidate.tvl_usd or 0.0)
        if apy > 99.0 and tvl < 1_000_000.0:
            demoted.append(candidate)
        else:
            kept.append(candidate)
    return kept + demoted


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
    primary = _apply_sanity_penalty(primary, request)
    limit = max(1, int(request.limit or 8))

    # Per-tier quota: when the user requested multiple risk levels, divide the
    # limit so each tier gets representation. Otherwise top-by-score wins
    # exclusively (fine for single-tier or unrestricted requests).
    requested_tiers = [t.upper() for t in (request.risk_levels or [])]
    if len(set(requested_tiers)) >= 2:
        per_tier = max(1, limit // len(set(requested_tiers)))
        bucketed: dict[str, list[OpportunityCandidate]] = {t: [] for t in set(requested_tiers)}
        leftover: list[OpportunityCandidate] = []
        for c in primary:
            t = (c.risk_level or "").upper()
            if t in bucketed and len(bucketed[t]) < per_tier:
                bucketed[t].append(c)
            else:
                leftover.append(c)
        merged: list[OpportunityCandidate] = []
        for t in set(requested_tiers):
            merged.extend(bucketed[t])
        merged.extend(leftover)
        limited = merged[:limit]
    else:
        limited = primary[:limit]

    return OpportunitySearchResult(primary=limited, excluded=excluded)
