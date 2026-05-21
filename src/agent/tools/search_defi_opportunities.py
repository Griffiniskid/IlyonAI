from __future__ import annotations

from typing import Any

from src.agent.protocol_urls import get_exec_capability, protocol_app_url
from src.agent.tools._base import err_envelope, ok_envelope
from src.defi.search.models import OpportunityCandidate, OpportunitySearchRequest
from src.defi.search.ranking import rank_opportunities
from src.defi.strategy.memory import remember_search_universe


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
    # Prefer the protocol's own app URL (where the user can actually deposit).
    # Fall back to DefiLlama's protocol page only if we have nothing else.
    app_url = protocol_app_url(protocol_slug, project_url=project_url)
    if app_url:
        urls["protocol_app"] = app_url
    elif protocol_slug:
        urls["defillama_protocol"] = f"https://defillama.com/protocol/{protocol_slug}"
    if project_url and project_url != app_url:
        urls["protocol_site"] = project_url
    return urls


def _infer_product_type(*, category: str | None, project_slug: str, symbol: str) -> str:
    """Map a DefiLlama pool to a Sentinel product_type label.

    DefiLlama returns category=None for many pools (notably every Solana pool
    as of 2026-05). Without inference our product_type filter excludes
    real LSTs, lending markets, etc. Fall back to project-slug + symbol heuristics.
    """
    if category:
        return str(category).lower()
    slug = (project_slug or "").lower()
    sym = (symbol or "").lower()
    # Liquid staking — most common LST naming on DefiLlama
    if any(k in slug for k in ("liquid-staking", "-lst", "lido", "jito", "marinade", "sanctum", "stader")):
        return "liquid staking"
    # Lending markets
    if any(k in slug for k in ("aave", "compound", "spark", "morpho", "kamino-lend", "save", "moonwell", "venus", "radiant")):
        return "lending"
    # Vaults
    if any(k in slug for k in ("yearn", "vault", "beefy", "idle")):
        return "vault"
    # Yield farms / aggregators
    if any(k in slug for k in ("farm", "yield-aggregator", "convex", "auto-compound")):
        return "yield aggregator"
    # Concentrated/AMM/DEX pools
    if any(k in slug for k in ("amm", "dex", "swap", "uniswap", "raydium", "orca", "meteora", "curve", "balancer", "velodrome", "aerodrome")):
        return "pool"
    # Pendle PT/YT
    if "pendle" in slug or sym.startswith("pt-"):
        return "yield"
    return "pool"


def _candidate_from_defillama(pool: dict[str, Any]) -> OpportunityCandidate:
    apy = float(pool.get("apy") or 0.0)
    tvl = float(pool.get("tvlUsd") or pool.get("tvl_usd") or 0.0)
    raw_chain = str(pool.get("chain") or "unknown")
    chain = _canonical_chain(raw_chain) or raw_chain.lower()
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
        product_type=_infer_product_type(
            category=pool.get("category"),
            project_slug=protocol_slug,
            symbol=str(pool.get("symbol") or ""),
        ),
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


_CHAIN_ALIAS_MAP = {
    "eth": "ethereum",
    "ether": "ethereum",
    "ethereum": "ethereum",
    "mainnet": "ethereum",
    "matic": "polygon",
    "polygon": "polygon",
    "pos": "polygon",
    "polygon-pos": "polygon",
    "bsc": "bsc",
    "bnb": "bsc",
    "binance": "bsc",
    "binance-smart-chain": "bsc",
    "sol": "solana",
    "solana": "solana",
    "arb": "arbitrum",
    "arbitrum": "arbitrum",
    "arbitrum-one": "arbitrum",
    "op": "optimism",
    "optimism": "optimism",
    "avax": "avalanche",
    "avalanche": "avalanche",
    "base": "base",
    "linea": "linea",
    "mantle": "mantle",
    "zksync": "zksync era",
    "zksync-era": "zksync era",
    "scroll": "scroll",
    "blast": "blast",
    "mode": "mode",
    "berachain": "berachain",
    "bera": "berachain",
    "sonic": "sonic",
    "sei": "sei",
    "ton": "ton",
    "aptos": "aptos",
    "sui": "sui",
    "tron": "tron",
    "fantom": "fantom",
    "ftm": "fantom",
    "celo": "celo",
    "near": "near",
    "cosmos": "cosmos",
    "osmosis": "osmosis",
    "injective": "injective",
    "kava": "kava",
    "cronos": "cronos",
    "metis": "metis",
    "gnosis": "gnosis",
    "xdai": "gnosis",
    "moonbeam": "moonbeam",
    "moonriver": "moonriver",
    "harmony": "harmony",
    "klaytn": "klaytn",
    "zora": "zora",
    "manta": "manta",
    "starknet": "starknet",
}


_DEFILLAMA_RAW_TO_CANONICAL = {
    "op mainnet": "optimism",
    "optimism": "optimism",
    "binance": "bsc",
    "binance smart chain": "bsc",
    "bnb smart chain": "bsc",
    "bnb chain": "bsc",
    "bsc": "bsc",
    "polygon zkevm": "polygon zkevm",
    "polygon pos": "polygon",
    "polygon": "polygon",
    "matic": "polygon",
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "arbitrum one": "arbitrum",
    "arbitrum nova": "arbitrum nova",
    "avalanche": "avalanche",
    "avax": "avalanche",
    "base": "base",
    "solana": "solana",
    "linea": "linea",
    "mantle": "mantle",
    "zksync era": "zksync era",
    "scroll": "scroll",
    "blast": "blast",
    "mode": "mode",
    "berachain": "berachain",
    "sonic": "sonic",
    "sei": "sei",
    "ton": "ton",
    "aptos": "aptos",
    "sui": "sui",
    "tron": "tron",
    "fantom": "fantom",
    "celo": "celo",
    "near": "near",
    "cosmos": "cosmos",
    "osmosis": "osmosis",
    "injective": "injective",
    "kava": "kava",
    "cronos": "cronos",
    "metis": "metis",
    "gnosis": "gnosis",
    "moonbeam": "moonbeam",
    "moonriver": "moonriver",
    "harmony": "harmony",
    "klaytn": "klaytn",
    "zora": "zora",
    "manta": "manta",
    "starknet": "starknet",
    "hyperliquid l1": "hyperliquid",
    "hyperliquid": "hyperliquid",
    "monad": "monad",
    "katana": "katana",
    "cardano": "cardano",
}


def _canonical_chain(chain: str | None) -> str | None:
    if not chain:
        return None
    s = str(chain).strip().lower().replace("_", "-")
    if s in _CHAIN_ALIAS_MAP:
        return _CHAIN_ALIAS_MAP[s]
    if s in _DEFILLAMA_RAW_TO_CANONICAL:
        return _DEFILLAMA_RAW_TO_CANONICAL[s]
    # Try with hyphens collapsed to spaces
    s_space = s.replace("-", " ")
    if s_space in _DEFILLAMA_RAW_TO_CANONICAL:
        return _DEFILLAMA_RAW_TO_CANONICAL[s_space]
    return s


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


def _dedup_primary(primary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse same-protocol-same-symbol-same-chain entries, keeping the
    highest-TVL one. Different pool_ids of the same pair look like duplicates
    to a user and erode trust.
    """
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for it in primary:
        key = (
            (it.get("protocol") or "").lower(),
            (it.get("symbol") or "").upper(),
            (it.get("chain") or "").lower(),
        )
        cur = seen.get(key)
        if cur is None:
            seen[key] = it
            order.append(key)
        else:
            try:
                if float(it.get("tvl_usd") or 0) > float(cur.get("tvl_usd") or 0):
                    seen[key] = it
            except (TypeError, ValueError):
                pass
    return [seen[k] for k in order]


def _enforce_risk_mix(
    primary: list[dict[str, Any]],
    excluded_pool: list[OpportunityCandidate],
    request: OpportunitySearchRequest,
) -> list[dict[str, Any]]:
    """When request.risk_levels has multiple tiers, ensure the result contains
    at least one entry per requested tier — promote tier-survivors from the
    excluded pool if necessary.
    """
    wanted = {r.upper() for r in (request.risk_levels or [])}
    if len(wanted) < 2:
        return primary
    present = {(it.get("risk_level") or "").upper() for it in primary}
    missing = wanted - present
    if not missing:
        return primary
    # Find replacement candidates from excluded pool that match each missing tier
    promoted: list[dict[str, Any]] = list(primary)
    promoted_keys = {(it.get("protocol") or "", it.get("symbol") or "", it.get("chain") or "") for it in promoted}
    for tier in missing:
        # Search excluded for a candidate of this tier that wasn't excluded
        # purely on tier basis
        for cand in excluded_pool:
            if (cand.risk_level or "").upper() != tier:
                continue
            ck = (cand.protocol or "", cand.symbol or "", cand.chain or "")
            if ck in promoted_keys:
                continue
            d = cand.to_dict()
            promoted.append(d)
            promoted_keys.add(ck)
            break
    return promoted[: max(1, int(request.limit or 8))]


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
        protocol_label = item.get("protocol", "Protocol")
        if urls.get("protocol_app"):
            link_entries.append({"label": f"Open in {protocol_label}", "url": urls["protocol_app"]})
        elif urls.get("defillama_protocol"):
            link_entries.append({"label": f"{protocol_label} on DefiLlama", "url": urls["defillama_protocol"]})
        if urls.get("protocol_site") and urls.get("protocol_site") != urls.get("protocol_app"):
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
            "code": "UNSUPPORTED_ADAPTER",
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


_STABLE_TICKERS = {
    "USDC", "USDT", "DAI", "FRAX", "LUSD", "USDE", "SUSDE", "USDY", "PYUSD",
    "GHO", "TUSD", "BUSD", "FDUSD", "USDP", "MIM", "MUSD", "CRVUSD",
    "MKUSD", "AUSD", "USDD", "USDX", "SUSDS", "REUSDE", "MSUSD",
}


def _is_stable_pool(symbol: str) -> bool:
    """True when the pool's symbol is composed entirely of stable assets."""
    if not symbol:
        return False
    parts = [p for p in symbol.upper().replace("/", "-").replace("_", "-").split("-") if p]
    if not parts:
        return False
    return all(p in _STABLE_TICKERS or any(s in p for s in ("USD", "DAI", "FRAX")) for p in parts)


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
    stablecoin_only: bool = False,
    min_tvl: float | None = None,
    protocol_filter: str | None = None,
    exclude_pool_ids: list[str] | None = None,
):
    # When the caller asks for low-risk only, tighten the TVL floor and cap the
    # APY band so we don't surface high-APY low-TVL traps that look quantitatively
    # safe but are actually thin liquidity. "Conservative" in the user's words
    # should mean conservative in candidates too.
    risk_set = {r.upper() for r in (risk_levels or [])}
    # Floors mean "minimum TVL to be considered a non-trap candidate".
    # Conservative tier still filters thin liquidity, but high-tier traders
    # need access to the long tail down to ~$10K TVL pools.
    if risk_set == {"LOW"}:
        min_tvl_floor = 5_000_000.0
        max_apy_cap = 50.0 if max_apy is None else max_apy
    elif risk_set == {"MEDIUM"} or risk_set == {"LOW", "MEDIUM"}:
        min_tvl_floor = 500_000.0
        max_apy_cap = 300.0 if max_apy is None else max_apy
    else:
        min_tvl_floor = 10_000.0
        max_apy_cap = 10_000.0 if max_apy is None else max_apy
    # Caller-supplied min_tvl wins over the per-risk floor (used by refinements)
    if min_tvl is not None:
        try:
            min_tvl_floor = max(min_tvl_floor, float(min_tvl))
        except (TypeError, ValueError):
            pass
    # Defend against inverted APY bands BEFORE constructing the request so
    # the downstream trace string and apy_band card field both show the
    # corrected ordering. Pass A surfaced H11/H14/enso-02 emitting
    # `min_apy=0.5, max_apy=0.48` -> 0 candidates. The model layer also
    # guards this, but doing it here keeps the trace honest.
    if min_apy is not None and max_apy is not None:
        try:
            _a, _b = float(min_apy), float(max_apy)
            if _a > _b:
                min_apy, max_apy = min(_a, _b), max(_a, _b)
                max_apy_cap = max_apy
        except (TypeError, ValueError):
            pass
    canonical_chains = [_canonical_chain(c) for c in (chains or []) if c]
    canonical_chains = [c for c in canonical_chains if c]
    # F05 0-result trap fix: when protocol_filter narrows to a single
    # specific protocol (e.g. 'aerodrome'), restricting product_types to
    # a narrow set like ['vault'] over-filters the candidate pool to 0
    # because Aerodrome only has LP / dex pools (not vaults). The
    # protocol_filter is already the dominant constraint — drop the
    # product_types filter entirely so the protocol_filter survives the
    # ranking pass with non-zero candidates. Caller can re-narrow
    # downstream by reading the surfaced item.product_type field.
    effective_product_types = list(product_types or [])
    if protocol_filter and effective_product_types and len(effective_product_types) <= 2:
        effective_product_types = []
    # BUG-RC-009: 0% APY pools must not surface as "best". When the
    # caller does not specify a min_apy, apply an implicit 0.01% floor
    # so the ranker drops pools whose APY is literally zero (sky-lending
    # WETH / Sky-lending WSTETH surfaced as #3 and #5 "best" yield pools
    # with 0.0% APY in the AI Bug Convo.md transcript). Explicit
    # min_apy=0 still allowed for users who want to inspect 0% positions.
    _effective_min_apy = 0.01 if min_apy is None else min_apy
    request = OpportunitySearchRequest(
        risk_levels=risk_levels or [],
        chains=canonical_chains,
        product_types=effective_product_types,
        target_apy=target_apy,
        min_apy=_effective_min_apy,
        max_apy=max_apy_cap,
        min_tvl=min_tvl_floor,
        ranking_objective=ranking_objective,
        limit=limit,
        execution_requested=execution_requested,
        asset_hint=asset_hint,
    )
    defillama = getattr(ctx.services, "defillama", None)
    if defillama is None:
        return err_envelope("defillama_unavailable", "DefiLlama pool search is not available on this server.")

    # Single full-universe fetch — every chain, every protocol, every pool.
    # Chain restriction is enforced downstream in _candidate_exclusions against
    # the raw chain string returned by DefiLlama (handles Linea, Mantle, zkSync,
    # Berachain, Sonic, Sei, Blast, Mode, Scroll, etc. without an enum mapping).
    if hasattr(defillama, "get_all_pools_normalized"):
        raw_pools = await defillama.get_all_pools_normalized()
    else:
        raw_pools = await defillama.get_pools(chain=None, min_tvl=0, min_apy=0)
    candidates = [_candidate_from_defillama(pool) for pool in raw_pools]
    if stablecoin_only:
        candidates = [c for c in candidates if _is_stable_pool(c.symbol)]
    if exclude_pool_ids:
        excl = {str(p) for p in exclude_pool_ids if p}
        candidates = [c for c in candidates if str(c.pool_id or "") not in excl]
    if protocol_filter:
        pf = protocol_filter.lower()
        candidates = [c for c in candidates if pf in (c.protocol_slug or "").lower() or pf in (c.protocol or "").lower()]
    # Both badge (here) and exec gate (build_yield_execution_plan) consult
    # `get_exec_capability` so they cannot drift. The helper enforces
    # is_pool_link_action FIRST (matching the exec gate) before checking the
    # adapter registry — this prevents the "ready via enso-shortcut-fallback"
    # badge from being shown on pools that exec will redirect to pool_link.
    for candidate in candidates:
        action = "supply" if candidate.product_type in {"lending", "supply"} else (
            "deposit_lp" if candidate.product_type in {"pool", "lp"} else "stake"
        )
        protocol_key = candidate.protocol_slug or candidate.protocol
        cap = get_exec_capability(protocol_key, candidate.chain, action)
        if cap["executable"]:
            candidate.executable = True
            candidate.adapter_id = (
                "enso-shortcut-fallback" if cap["mode"] == "enso_fallback"
                else ("solana-yield-builder-fallback" if (candidate.chain or "").lower() in {"solana", "sol"} and cap["mode"] == "deterministic" and candidate.protocol_slug not in {"marinade", "jito", "sanctum"}
                      else cap["mode"])
            )
            candidate.unsupported_reason = None
            continue
        # Not executable — surface the helper's reason so badge and exec align.
        candidate.executable = False
        if cap["mode"] == "link_only":
            candidate.unsupported_reason = (
                f"{candidate.protocol} on {candidate.chain}: {cap['reason']}."
            )
        else:
            candidate.unsupported_reason = (
                f"No direct adapter for {candidate.protocol} on {candidate.chain}; "
                f"closest executable alternative will be substituted at execution time."
            )
    ranked = rank_opportunities(candidates, request)
    primary = [candidate.to_dict() for candidate in ranked.primary]
    primary = _dedup_primary(primary)
    primary = _enforce_risk_mix(
        primary,
        [e.candidate for e in ranked.excluded if "risk_not_requested" in (e.reason_codes or [])],
        request,
    )
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
        "request_meta": {
            "target_apy": request.target_apy,
            "min_apy": request.min_apy,
            "max_apy": request.max_apy,
            "risk_levels": list(request.risk_levels or []),
            "chains": list(request.chains or []),
            "product_types": list(request.product_types or []),
            "stablecoin_only": stablecoin_only,
        },
    }
    # RC14: cache the ranked universe per session so a downstream
    # build_yield_execution_plan adapter-build failure can populate
    # recovery.alternatives from candidates the user has already seen.
    session_id = getattr(ctx, "session_id", None) if ctx is not None else None
    if session_id and primary:
        try:
            remember_search_universe(str(session_id), primary)
        except Exception:  # noqa: BLE001 — cache is best-effort
            pass

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
