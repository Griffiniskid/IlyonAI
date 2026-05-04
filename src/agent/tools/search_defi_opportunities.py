from __future__ import annotations

from typing import Any

from src.agent.tools._base import err_envelope, ok_envelope
from src.defi.execution.capabilities import build_default_registry
from src.defi.search.models import OpportunityCandidate, OpportunitySearchRequest
from src.defi.search.ranking import rank_opportunities


def _infer_risk_level(*, apy: float, tvl_usd: float) -> str:
    if apy >= 80.0 or tvl_usd < 1_000_000:
        return "HIGH"
    if apy >= 25.0 or tvl_usd < 50_000_000:
        return "MEDIUM"
    return "LOW"


def _build_source_urls(*, protocol_slug: str, pool_id: str | None, project_url: str | None) -> dict[str, str]:
    urls: dict[str, str] = {}
    if pool_id:
        urls["defillama_pool"] = f"https://defillama.com/yields/pool/{pool_id}"
    if protocol_slug:
        urls["defillama_protocol"] = f"https://defillama.com/protocol/{protocol_slug}"
    if project_url:
        urls["protocol_site"] = project_url
    return urls


def _candidate_from_defillama(pool: dict[str, Any]) -> OpportunityCandidate:
    apy = float(pool.get("apy") or 0.0)
    tvl = float(pool.get("tvlUsd") or pool.get("tvl_usd") or 0.0)
    chain = str(pool.get("chain") or "unknown")
    protocol = str(pool.get("project") or "Unknown")
    protocol_slug = protocol.lower().replace(" ", "-").replace(".", "-")
    pool_id = str(pool.get("pool") or pool.get("pool_id") or "") or None
    risk_level = str(pool.get("risk_level") or _infer_risk_level(apy=apy, tvl_usd=tvl)).upper()
    project_url = pool.get("url") or None
    underlying = pool.get("underlyingTokens") or pool.get("underlying_tokens") or []
    return OpportunityCandidate(
        source_id=pool_id,
        source="DefiLlama",
        protocol=protocol,
        protocol_slug=protocol_slug,
        chain=chain,
        product_type=str(pool.get("category") or "pool").lower(),
        symbol=str(pool.get("symbol") or "Unknown"),
        pool_id=pool_id,
        token_addresses=[str(token) for token in underlying if token],
        apy=apy,
        apy_base=pool.get("apyBase"),
        apy_reward=pool.get("apyReward"),
        tvl_usd=tvl,
        volume_24h_usd=float(pool.get("volumeUsd1d") or pool.get("volume_usd_1d") or 0.0) or None,
        risk_level=risk_level,
        source_urls=_build_source_urls(protocol_slug=protocol_slug, pool_id=pool_id, project_url=project_url),
        executable=False,
        unsupported_reason="No verified execution adapter is available for this opportunity yet.",
    )


def _chain_type(chain: str | None):
    if not chain:
        return None
    try:
        from src.chains.base import ChainType
    except Exception:
        return None
    mapping = {
        "ethereum": ChainType.ETHEREUM,
        "eth": ChainType.ETHEREUM,
        "solana": ChainType.SOLANA,
        "sol": ChainType.SOLANA,
        "bsc": ChainType.BSC,
        "polygon": ChainType.POLYGON,
        "arbitrum": ChainType.ARBITRUM,
        "optimism": ChainType.OPTIMISM,
        "avalanche": ChainType.AVALANCHE,
        "base": ChainType.BASE,
    }
    return mapping.get(chain.lower())


def _opportunity_card_payload(
    primary: list[dict[str, Any]],
    *,
    request: OpportunitySearchRequest,
    excluded_count: int,
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in primary[:8]:
        urls = item.get("source_urls") or {}
        link_entries: list[dict[str, str]] = []
        if urls.get("defillama_pool"):
            link_entries.append({"label": "DefiLlama pool", "url": urls["defillama_pool"]})
        if urls.get("defillama_protocol"):
            link_entries.append({"label": f"{item.get('protocol', 'Protocol')} on DefiLlama", "url": urls["defillama_protocol"]})
        if urls.get("protocol_site"):
            link_entries.append({"label": "Protocol site", "url": urls["protocol_site"]})
        items.append({
            "protocol": item.get("protocol"),
            "symbol": item.get("symbol"),
            "chain": item.get("chain"),
            "product_type": item.get("product_type"),
            "apy": item.get("apy"),
            "apy_base": item.get("apy_base"),
            "apy_reward": item.get("apy_reward"),
            "tvl_usd": item.get("tvl_usd"),
            "volume_24h_usd": item.get("volume_24h_usd"),
            "risk_level": item.get("risk_level"),
            "executable": item.get("executable"),
            "adapter_id": item.get("adapter_id"),
            "unsupported_reason": item.get("unsupported_reason"),
            "links": link_entries,
            "pool_id": item.get("pool_id"),
        })
    return {
        "objective": request.ranking_objective,
        "target_apy": request.target_apy,
        "apy_band": [request.min_apy, request.max_apy],
        "risk_levels": request.risk_levels,
        "chains": request.chains,
        "execution_requested": request.execution_requested,
        "items": items,
        "excluded_count": excluded_count,
        "blockers": blockers,
    }


def _execution_blockers(primary: list[dict[str, Any]], request: OpportunitySearchRequest) -> list[dict[str, Any]]:
    if not request.execution_requested:
        return []
    executable = [candidate for candidate in primary if candidate.get("executable")]
    if executable:
        return []
    protocol = primary[0]["protocol"] if primary else "the selected opportunity"
    chain = primary[0]["chain"] if primary else (request.chains[0] if request.chains else "requested chain")
    return [
        {
            "code": "unsupported_adapter",
            "severity": "blocker",
            "title": "Direct execution is not supported yet",
            "detail": (
                f"{protocol} on {chain} is research-only right now. I will not expose a signing button "
                "until a verified adapter can build real unsigned transactions and post-deposit verification."
            ),
            "affected_step_ids": ["deposit"],
            "recoverable": True,
            "cta": "Use this as research, or ask for supported EVM staking/swap/bridge routes.",
        }
    ]


async def search_defi_opportunities(
    ctx,
    *,
    risk_levels: list[str] | None = None,
    target_apy: float | None = None,
    min_apy: float | None = None,
    max_apy: float | None = None,
    chains: list[str] | None = None,
    product_types: list[str] | None = None,
    asset_hint: str | None = None,
    ranking_objective: str = "constraint_fit_then_risk_adjusted_return",
    execution_requested: bool = False,
    limit: int = 8,
):
    request = OpportunitySearchRequest(
        risk_levels=risk_levels or [],
        chains=chains or [],
        product_types=product_types or [],
        target_apy=target_apy,
        min_apy=0.5 if min_apy is None else min_apy,
        max_apy=500.0 if max_apy is None else max_apy,
        min_tvl=100_000.0,
        ranking_objective=ranking_objective,
        limit=limit,
        execution_requested=execution_requested,
        asset_hint=asset_hint,
    )
    defillama = getattr(ctx.services, "defillama", None)
    if defillama is None:
        return err_envelope("defillama_unavailable", "DefiLlama pool search is not available on this server.")

    raw_pools: list[dict[str, Any]] = []
    chains_to_query = request.chains or [None]
    for chain in chains_to_query:
        raw_pools.extend(await defillama.get_pools(
            chain=_chain_type(chain),
            min_tvl=request.min_tvl,
            min_apy=max(0.0, float(request.min_apy or 0.5)),
        ))
    candidates = [_candidate_from_defillama(pool) for pool in raw_pools]
    registry = build_default_registry()
    for candidate in candidates:
        action = "supply" if candidate.product_type in {"lending", "supply"} else (
            "deposit_lp" if candidate.product_type in {"pool", "lp"} else "stake"
        )
        verdict = registry.find(chain=candidate.chain, protocol=candidate.protocol_slug or candidate.protocol, action=action)
        if verdict.supported:
            candidate.executable = True
            candidate.adapter_id = verdict.adapter_id
            candidate.unsupported_reason = None
            continue
        # Try the catch-all Enso adapter on EVM, or the Solana sidecar by chain.
        chain_lower = candidate.chain.lower()
        fallback_action = "supply" if candidate.product_type in {"lending", "supply", "vault"} else "deposit_lp"
        if chain_lower in {"ethereum", "polygon", "arbitrum", "optimism", "base", "avalanche", "bsc"}:
            fallback = registry.find(chain=chain_lower, protocol="yearn-finance", action=fallback_action)
            if fallback.supported:
                candidate.executable = True
                candidate.adapter_id = "enso-shortcut-fallback"
                candidate.unsupported_reason = None
                continue
        if chain_lower in {"solana", "sol"}:
            fallback = registry.find(chain="solana", protocol="kamino", action="supply")
            if fallback.supported:
                candidate.executable = True
                candidate.adapter_id = "solana-yield-builder-fallback"
                candidate.unsupported_reason = None
                continue
        # Last resort — keep candidate but mark as needing manual route.
        candidate.executable = False
        candidate.unsupported_reason = (
            f"No direct adapter for {candidate.protocol} on {candidate.chain}; "
            f"closest executable alternative will be substituted at execution time."
        )
    ranked = rank_opportunities(candidates, request)
    primary = [candidate.to_dict() for candidate in ranked.primary]
    excluded = [item.to_dict() for item in ranked.excluded[:25]]
    blockers = _execution_blockers(primary, request)
    executable_count = sum(1 for candidate in primary if candidate.get("executable"))
    trace = [
        f"Parsed constraints: risk={request.risk_levels or 'any'}, target_apy={request.target_apy}, apy_band=({request.min_apy}, {request.max_apy}).",
        f"Queried DefiLlama with min_tvl=${request.min_tvl:,.0f} and min_apy={request.min_apy} instead of the legacy $200M/0.5% staking defaults.",
        f"Ranked {len(candidates)} candidates by {request.ranking_objective}; {len(primary)} matched the hard constraints and {len(excluded)} were excluded.",
    ]
    if blockers:
        trace.append("Execution request is blocked because no verified adapter can build unsigned pool transactions for the selected candidates.")

    data = {
        "primary_candidates": primary,
        "research_trace": trace,
        "analysis_trace": trace,
        "excluded_summary": excluded,
        "source_summary": {"DefiLlama": len(candidates)},
        "execution_requested": execution_requested,
        "execution_readiness_summary": {
            "executable_count": executable_count,
            "research_only_count": max(0, len(primary) - executable_count),
        },
        "execution_blockers": blockers,
    }
    return ok_envelope(
        data=data,
        card_type="defi_opportunities" if primary else None,
        card_payload=_opportunity_card_payload(
            primary,
            request=request,
            excluded_count=len(excluded),
            blockers=blockers,
        ) if primary else None,
    )
