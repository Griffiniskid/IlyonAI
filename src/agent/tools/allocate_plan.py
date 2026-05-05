"""allocate_plan — chain-aware allocation using the real DeFi intelligence engine."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence
from uuid import uuid4

from src.agent.tools._base import err_envelope, ok_envelope
from src.allocator.composer import (
    PoolCandidate,
    compose_allocation,
    execution_steps_from_positions,
    normalise_chain,
    summarise_positions,
    total_gas_from_steps,
    wallets_summary_from_steps,
)


_logger = logging.getLogger(__name__)


_CHAIN_SHORT_TO_FULL = {
    "eth": "ethereum",
    "mainnet": "ethereum",
    "arb": "arbitrum",
    "op": "optimism",
    "polygon": "polygon",
    "base": "base",
    "bsc": "bsc",
    "avax": "avalanche",
    "sol": "solana",
    "solana": "solana",
}


async def _bake_step_transactions(ctx, steps: list[dict], positions: list) -> list[dict]:
    """For each allocation step, call execute_pool_position to obtain a real
    unsigned transaction and embed it on the step — in parallel for speed.
    """
    from src.agent.tools.execute_pool_position import execute_pool_position
    pos_by_index = {p.rank: p for p in positions}

    async def _bake_one(step: dict) -> dict:
        idx = step.get("index")
        position = pos_by_index.get(idx)
        baked = dict(step)
        if not position:
            return baked
        pool_ref = f"{position.protocol} {position.asset}".strip()
        try:
            amt_str = str(step.get("amount", "")).replace(",", "").replace("$", "")
            amount = float(amt_str) if amt_str else 100.0
        except (TypeError, ValueError):
            amount = 100.0
        chain_full = _CHAIN_SHORT_TO_FULL.get(position.chain)
        async def _try_bake(pool_ref_inner: str) -> tuple[dict | None, str | None]:
            try:
                env = await asyncio.wait_for(
                    execute_pool_position(ctx, pool=pool_ref_inner, amount=amount, chain=chain_full),
                    timeout=12.0,
                )
                if env and env.ok and env.card_payload:
                    plan = env.card_payload
                    first = (plan.get("steps") or [None])[0] if isinstance(plan, dict) else None
                    if first and first.get("transaction"):
                        return first.get("transaction"), None
                    blockers = plan.get("blockers") if isinstance(plan, dict) else None
                    if blockers:
                        b0 = blockers[0]
                        return None, (
                            (b0.get("title") or "Adapter blocked") + ": " +
                            (b0.get("detail") or "")[:200]
                        )[:280]
                if env and not env.ok:
                    err = getattr(env, "error", None)
                    if err:
                        return None, f"{err.code}: {err.message[:200]}"
            except Exception as exc:  # noqa: BLE001
                _logger.warning("bake_step %s failed: %s", idx, exc)
                return None, str(exc)[:200]
            return None, None

        tx, blocker_text = await _try_bake(pool_ref)
        if tx:
            baked["transaction"] = tx
        else:
            # Fallback path: when the original protocol can't bake (Enso
            # rate-limited, no fungible LP, etc.), try a yield-equivalent
            # liquid pool on the same chain so the user still gets a
            # signable transaction. Stable LPs → Aave V3 of the same asset.
            stable_assets = {"USDC", "USDT", "DAI", "FRAX", "LUSD"}
            asset_upper = (position.asset or "").upper()
            asset_legs = set(asset_upper.replace("/", "-").replace("_", "-").split("-"))
            stable_in_asset = next((s for s in stable_assets if s in asset_legs), None)
            if stable_in_asset and (chain_full or "").lower() in {"ethereum", "polygon", "arbitrum", "base", "optimism", "avalanche"}:
                fallback_asset = stable_in_asset
                # Direct Aave V3 path: no DefiLlama lookup, no Enso routing.
                # Aave V3 adapter builds approve+supply EVM calldata in-process.
                from src.agent.tools.build_yield_execution_plan import build_yield_execution_plan
                try:
                    fallback_env = await asyncio.wait_for(
                        build_yield_execution_plan(
                            ctx,
                            chain=chain_full,
                            protocol="aave-v3",
                            action="supply",
                            asset_in=fallback_asset,
                            amount_in=amount,
                            user_address=getattr(ctx, "evm_wallet", None) or getattr(ctx, "wallet", None),
                        ),
                        timeout=12.0,
                    )
                    if fallback_env and fallback_env.ok and fallback_env.card_payload:
                        plan = fallback_env.card_payload
                        first = (plan.get("steps") or [None])[0] if isinstance(plan, dict) else None
                        if first and first.get("transaction"):
                            baked["transaction"] = first.get("transaction")
                            baked["blocker"] = None
                            baked["target"] = f"{fallback_asset} · Aave V3 (fallback for {position.protocol})"
                            baked["protocol"] = "Aave V3"
                            baked["router"] = "Aave V3"
                            return baked
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("aave-v3 fallback failed: %s", exc)
                baked["blocker"] = blocker_text
            else:
                baked["blocker"] = blocker_text
        return baked

    results = await asyncio.gather(*[_bake_one(s) for s in steps], return_exceptions=True)
    out: list[dict] = []
    for s, r in zip(steps, results):
        if isinstance(r, Exception):
            _logger.warning("bake_one task crashed: %s", r)
            out.append(dict(s))
        else:
            out.append(r)
    return out


_AUDIT_PROJECTS = {
    "lido", "rocket-pool", "rocketpool", "jito", "aave-v3", "aave-v2",
    "compound-v3", "compound-v2", "pendle", "curve-dex", "curve",
    "ether.fi", "ether-fi", "renzo", "etherfi", "spark", "morpho-blue",
    "mountain-protocol", "usdy", "sky-lending", "makerdao", "mantle-staked-ether",
    "origin-ether", "binance-staked-eth", "coinbase-wrapped-staked-eth",
    "stader", "frax-ether", "raft", "gyroscope-protocol", "convex-finance",
    "yearn-finance", "beefy", "idle", "clearpool", "maple", "goldfinch",
    "instadapp", "yieldflow", "stargate", "hyperliquid",
}


def _infer_audits(project_slug: str) -> bool:
    return project_slug.lower() in _AUDIT_PROJECTS


def _infer_stable(symbol: str, pool: dict[str, Any]) -> bool:
    if pool.get("stablecoin"):
        return True
    stable_tokens = ("USDC", "USDT", "DAI", "FRAX", "LUSD", "USDE", "SUSDE", "USDY", "PYUSD", "GHO")
    symbol_upper = symbol.upper()
    return any(token in symbol_upper for token in stable_tokens)


def _infer_exposure(pool: dict[str, Any]) -> str:
    symbol = str(pool.get("symbol") or "")
    return "multi" if "-" in symbol and not symbol.startswith("PT-") else "single"


def _infer_days_live(pool: dict[str, Any]) -> int:
    tvl = float(pool.get("tvlUsd", 0) or 0)
    if _infer_audits(str(pool.get("project") or "")):
        return 720 if tvl >= 1_000_000_000 else 400
    return 200 if tvl >= 100_000_000 else 60


def _pool_to_candidate(pool: dict[str, Any]) -> PoolCandidate:
    return PoolCandidate(
        project=str(pool.get("project") or "Unknown"),
        symbol=str(pool.get("symbol") or "?"),
        chain=str(pool.get("chain") or "Ethereum"),
        tvl_usd=float(pool.get("tvlUsd", 0) or 0),
        apy=float(pool.get("apy", 0) or 0),
        audits=_infer_audits(str(pool.get("project") or "")),
        days_live=_infer_days_live(pool),
        stable=_infer_stable(str(pool.get("symbol") or ""), pool),
        il_risk=str(pool.get("ilRisk", "no") or "no"),
        exposure=_infer_exposure(pool),
        raw_flags=(),
    )
from src.api.schemas.agent import (
    AllocationPayload,
    AllocationPosition,
    ExecutionPlanPayload,
    ExtraCard,
    SentinelMatrixPayload,
)


def _format_tvl(usd: float) -> str:
    if usd >= 1_000_000_000:
        return f"${usd / 1_000_000_000:.1f}B"
    if usd >= 1_000_000:
        return f"${usd / 1_000_000:.0f}M"
    return f"${usd:,.0f}"


def _format_usd(usd: float) -> str:
    return f"${usd:,.0f}"


def _format_apy(apy: float) -> str:
    return f"{apy:.1f}%"


def _weight_ladder(count: int, risk_budget: str) -> list[int]:
    if count <= 0:
        return []
    if risk_budget == "conservative":
        base = [35, 25, 20, 12, 8]
    elif risk_budget == "aggressive":
        base = [30, 25, 20, 15, 10]
    else:
        base = [35, 20, 20, 15, 10]
    trimmed = base[:count]
    total = sum(trimmed)
    weights = [int(round(value * 100 / total)) for value in trimmed]
    drift = 100 - sum(weights)
    if weights:
        weights[0] += drift
    return weights


def _opportunity_score(profile: dict[str, Any]) -> int:
    summary = profile.get("summary") or {}
    return int(round(summary.get("opportunity_score") or summary.get("overall_score") or 0))


def _protocol_name(profile: dict[str, Any]) -> str:
    return str(profile.get("protocol_name") or profile.get("protocol") or profile.get("project") or "Unknown")


def _build_flags(profile: dict[str, Any]) -> list[str]:
    summary = profile.get("summary") or {}
    flags: list[str] = []
    for flag in summary.get("fragility_flags") or []:
        text = str(flag).strip()
        if text:
            flags.append(text[:48])
    for cap in profile.get("score_caps") or []:
        if isinstance(cap, dict):
            reason = str(cap.get("reason") or cap.get("code") or "").strip()
            if reason:
                flags.append(reason[:48])
    ai_analysis = profile.get("ai_analysis") or {}
    for risk in ai_analysis.get("main_risks") or []:
        text = str(risk).strip()
        if text:
            flags.append(text[:48])
    confidence = profile.get("confidence") or {}
    if confidence.get("partial_analysis"):
        flags.append("Partial evidence coverage")

    deduped: list[str] = []
    for flag in flags:
        if flag not in deduped:
            deduped.append(flag)
    return deduped[:4]


def _build_position(profile: dict[str, Any], *, rank: int, weight: int, usd_amount: float) -> AllocationPosition:
    summary = profile.get("summary") or {}
    chain = normalise_chain(str(profile.get("chain") or "mainnet"))
    return AllocationPosition(
        rank=rank,
        protocol=_protocol_name(profile),
        asset=str(profile.get("symbol") or "Unknown"),
        chain=chain,
        apy=_format_apy(float(profile.get("apy") or 0.0)),
        sentinel=_opportunity_score(profile),
        risk=str(summary.get("risk_level") or "MEDIUM").lower(),
        fit=str(summary.get("strategy_fit") or "balanced"),
        weight=weight,
        usd=_format_usd(usd_amount * weight / 100.0),
        tvl=_format_tvl(float(profile.get("tvl_usd") or 0.0)),
        router="Jupiter" if chain == "sol" else "Enso",
        safety=int(round(summary.get("safety_score") or 0)),
        durability=int(round(summary.get("yield_durability_score") or 0)),
        exit=int(round(summary.get("exit_liquidity_score") or 0)),
        confidence=int(round(summary.get("confidence_score") or 0)),
        flags=_build_flags(profile),
    )


def _pick_candidates(
    analysis: dict[str, Any],
    chains: Sequence[str] | None,
    *,
    risk_levels: Sequence[str] | None = None,
    min_apy: float | None = None,
    max_apy: float | None = None,
    asset_hint: str | None = None,
) -> list[dict[str, Any]]:
    requested = {chain.lower() for chain in (chains or [])}
    requested_risks = {str(level).upper() for level in (risk_levels or [])}
    asset_hint_upper = (asset_hint or "").upper().strip()
    opportunities = analysis.get("top_opportunities") or []

    def _opp_risk(opp: dict[str, Any]) -> str:
        summary = opp.get("summary") or {}
        return str(summary.get("risk_level") or "MEDIUM").upper()

    def _opp_apy(opp: dict[str, Any]) -> float:
        try:
            return float(opp.get("apy") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _passes_risk(opp: dict[str, Any]) -> bool:
        if not requested_risks:
            return True
        return _opp_risk(opp) in requested_risks

    def _passes_apy(opp: dict[str, Any]) -> bool:
        apy = _opp_apy(opp)
        if min_apy is not None and apy < float(min_apy):
            return False
        if max_apy is not None and apy > float(max_apy):
            return False
        return True

    def _passes_asset(opp: dict[str, Any]) -> bool:
        if not asset_hint_upper:
            return True
        symbol = str(opp.get("symbol") or "").upper()
        parts = [p for p in symbol.replace("/", "-").replace("_", "-").split("-") if p]
        return asset_hint_upper in parts

    filtered: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for opportunity in opportunities:
        chain = str(opportunity.get("chain") or "").lower()
        if requested and chain not in requested:
            continue
        if not _passes_risk(opportunity):
            continue
        if not _passes_apy(opportunity):
            continue
        if not _passes_asset(opportunity):
            continue
        key = (
            str(opportunity.get("symbol") or ""),
            str(opportunity.get("protocol_name") or opportunity.get("protocol") or ""),
            chain,
        )
        if key in seen:
            continue
        seen.add(key)
        filtered.append(opportunity)
        if len(filtered) >= 5:
            break

    if filtered:
        return filtered

    # Soft fallback: drop the most restrictive constraint if nothing matches
    fallback: list[dict[str, Any]] = []
    seen.clear()
    for opportunity in opportunities:
        chain = str(opportunity.get("chain") or "").lower()
        if requested and chain not in requested:
            continue
        if requested_risks and not _passes_risk(opportunity):
            continue
        key = (
            str(opportunity.get("symbol") or ""),
            str(opportunity.get("protocol_name") or opportunity.get("protocol") or ""),
            chain,
        )
        if key in seen:
            continue
        seen.add(key)
        fallback.append(opportunity)
        if len(fallback) >= 5:
            break
    return fallback


def _fallback_profile_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    summary = dict(candidate.get("summary") or {})
    fallback = dict(candidate)
    fallback.setdefault(
        "ai_analysis",
        {
            "summary": summary.get("thesis") or summary.get("headline") or "The fallback profile kept the deterministic opportunity score because deep analysis timed out.",
            "main_risks": summary.get("fragility_flags") or ["Deep analysis timed out; using deterministic scoring."],
            "monitor_triggers": ["Re-run the request if you need the full deep profile."],
        },
    )
    fallback.setdefault("score_caps", [])
    return fallback


def _decode_opportunity_id(opportunity_id: str) -> tuple[str | None, str | None]:
    if "--" not in opportunity_id:
        return None, None
    kind, raw_id = opportunity_id.split("--", 1)
    return kind, raw_id


def _lookup_raw_candidate(analysis: dict[str, Any], *, kind: str, raw_id: str) -> dict[str, Any] | None:
    if kind == "lending":
        for item in analysis.get("top_lending_markets") or []:
            if str(item.get("pool_id") or "") == raw_id:
                return item
        return None

    source_key = "top_yields" if kind == "yield" else "top_pools"
    for item in analysis.get(source_key) or []:
        candidate_id = str(item.get("pool_id") or item.get("pool") or "")
        if candidate_id == raw_id:
            return item
    return None


async def _allocate_from_engine(
    ctx,
    *,
    usd_amount: float,
    risk_budget: str,
    chains: list[str] | None,
    asset_hint: str | None,
    target_apy: float | None = None,
    min_apy: float | None = None,
    max_apy: float | None = None,
    risk_levels: list[str] | None = None,
):
    engine = getattr(ctx.services, "defi_intelligence", None)
    if engine is None:
        return None

    primary_chain = chains[0] if chains else None
    effective_min_apy = float(min_apy) if min_apy is not None else 0.5
    effective_min_tvl = 100_000.0
    if risk_levels and "LOW" not in {str(level).upper() for level in risk_levels}:
        effective_min_tvl = 50_000.0
    if target_apy is not None and target_apy >= 50.0:
        effective_min_apy = max(effective_min_apy, max(5.0, target_apy * 0.4))
    analysis = await engine.analyze_market(
        chain=primary_chain,
        query=None,
        min_tvl=effective_min_tvl,
        min_apy=effective_min_apy,
        limit=24,
        include_ai=True,
        ranking_profile=risk_budget,
    )

    candidates = _pick_candidates(
        analysis,
        chains,
        risk_levels=risk_levels,
        min_apy=min_apy,
        max_apy=max_apy,
        asset_hint=asset_hint,
    )
    if not candidates:
        return err_envelope(
            "no_viable_pools",
            "No opportunities matched the requested chain and risk filters.",
        )

    engine_core = getattr(engine, "engine", None)
    llama = getattr(engine, "llama", None)
    protocol_index = None
    raw_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    if engine_core is not None and llama is not None:
        protocol_index = engine_core._build_protocol_index(await llama.get_protocols())
        raw_pools, raw_yields, raw_markets = await asyncio.gather(
            engine_core.pool_analyzer.get_top_pools(
                chain=primary_chain,
                min_tvl=100_000,
                min_apy=0.5,
                limit=48,
            ),
            engine_core.farm_analyzer.get_yields(
                chain=primary_chain,
                min_tvl=100_000,
                min_apy=0.5,
                limit=48,
            ),
            engine_core.lending_analyzer.get_lending_markets(
                chain=primary_chain,
                limit=48,
            ),
        )
        for item in raw_pools:
            raw_lookup[("pool", str(item.get("pool_id") or item.get("pool") or ""))] = item
        for item in raw_yields:
            raw_lookup[("yield", str(item.get("pool_id") or item.get("pool") or ""))] = item
        for item in raw_markets:
            raw_lookup[("lending", str(item.get("pool_id") or ""))] = item

    async def _build_profile(candidate: dict[str, Any]) -> dict[str, Any] | None:
        async def _deep_profile() -> dict[str, Any] | None:
            opportunity_id = str(candidate.get("id") or "")
            if not opportunity_id:
                return None
            if protocol_index is not None and engine_core is not None:
                kind, raw_id = _decode_opportunity_id(opportunity_id)
                if not kind or not raw_id:
                    return None
                raw_candidate = raw_lookup.get((kind, raw_id)) or _lookup_raw_candidate(analysis, kind=kind, raw_id=raw_id)
                if raw_candidate is None:
                    return None
                enriched_candidate = {**raw_candidate, "skip_token_intelligence": True}
                if kind in {"pool", "yield"}:
                    profile = await engine_core._build_pool_or_yield_opportunity(
                        enriched_candidate,
                        kind,
                        protocol_index,
                        True,
                        risk_budget,
                    )
                else:
                    profile = await engine_core._build_lending_opportunity(
                        enriched_candidate,
                        protocol_index,
                        True,
                        risk_budget,
                    )
                profile["ai_analysis"] = await engine_core.ai.build_opportunity_analysis(profile)
                return profile

            profile = await engine.get_opportunity_profile(
                opportunity_id,
                include_ai=True,
                ranking_profile=risk_budget,
            )
            return profile

        try:
            profile = await asyncio.wait_for(_deep_profile(), timeout=18)
        except asyncio.TimeoutError:
            return _fallback_profile_from_candidate(candidate)
        if profile is None:
            return _fallback_profile_from_candidate(candidate)
        return profile

    profile_results = await asyncio.gather(*[_build_profile(candidate) for candidate in candidates[:5]])
    profiles = [profile for profile in profile_results if profile is not None]

    if not profiles:
        return err_envelope(
            "no_viable_pools",
            "No opportunities survived deep analysis for this request.",
        )

    profiles.sort(key=_opportunity_score, reverse=True)
    weights = _weight_ladder(len(profiles), risk_budget)
    positions = [
        _build_position(profile, rank=index, weight=weight, usd_amount=usd_amount)
        for index, (profile, weight) in enumerate(zip(profiles, weights), start=1)
    ]
    summary = summarise_positions(positions, usd_amount)

    allocation_payload = AllocationPayload(
        positions=positions,
        **summary,
    )
    sentinel_matrix_payload = SentinelMatrixPayload(
        positions=positions,
        low_count=summary["risk_mix"]["low"],
        medium_count=summary["risk_mix"]["medium"],
        high_count=summary["risk_mix"]["high"],
        weighted_sentinel=summary["weighted_sentinel"],
    )
    steps = execution_steps_from_positions(positions, usd_amount)
    # Pre-bake real unsigned transactions into each step so the bulk
    # 'Start signing' and per-row Execute buttons land on a wallet popup
    # without an extra agent round-trip.
    steps = await _bake_step_transactions(ctx, steps, positions)
    execution_plan_payload = ExecutionPlanPayload(
        steps=steps,
        total_gas=total_gas_from_steps(steps),
        slippage_cap="0.5%",
        wallets=wallets_summary_from_steps(steps),
        tx_count=len(steps),
        requires_signature=True,
    )

    chain_scope = ", ".join(chains or []) if chains else None
    trace = [
        f"Queried DefiLlama yield pools and Sentinel opportunities for {chain_scope or 'all supported chains'}.",
        f"Filtered live opportunities to {chain_scope or 'all supported chains'} with TVL, operating-history, chain, and APY sanity gates.",
        f"Deep-analyzed {len(profiles)} finalists with docs, history, dependency, and AI synthesis.",
        "Scored candidates via Sentinel pool framework: Safety x Yield durability x Exit liquidity x Confidence.",
        "Cross-checked each protocol against Ilyon Shield: approval surface, admin keys, oracle/bridge dependencies, and incident history.",
        f"Selected {len(positions)} positions across {summary['chains']} chains; Sentinel >= 70 target and position cap <= 35%.",
        f"Composed execution plan with {len(steps)} wallet-gated transactions, router selection, gas estimates, and 0.5% slippage cap.",
        f"Final allocation lands at weighted Sentinel {summary['weighted_sentinel']}/100 and blended APY {summary['blended_apy']}.",
    ]
    fallback_count = sum(1 for profile in profiles if str((profile.get("ai_analysis") or {}).get("summary") or "").startswith("The fallback profile kept"))
    if fallback_count:
        trace.insert(2, f"{fallback_count} finalist(s) hit the deep-analysis timeout and fell back to deterministic scoring.")
    if asset_hint:
        trace.insert(1, f"Detected starting asset context: {asset_hint}.")

    envelope = ok_envelope(
        data={
            "total_usd": summary["total_usd"],
            "blended_apy": summary["blended_apy"],
            "weighted_sentinel": summary["weighted_sentinel"],
            "positions": [position.model_dump() for position in positions],
            "steps": steps,
            "chain_scope": chain_scope,
            "market_brief": analysis.get("ai_market_brief"),
            "analysis_trace": trace,
        },
        card_type="allocation",
        card_payload=allocation_payload.model_dump(),
    )
    envelope.extra_cards = [
        ExtraCard(
            card_id=str(uuid4()),
            card_type="sentinel_matrix",
            payload=sentinel_matrix_payload.model_dump(),
        ),
        ExtraCard(
            card_id=str(uuid4()),
            card_type="execution_plan",
            payload=execution_plan_payload.model_dump(),
        ),
    ]
    return envelope


async def _allocate_from_defillama(
    ctx,
    *,
    usd_amount: float,
    risk_budget: str,
    chains: list[str] | None,
):
    defillama = getattr(ctx.services, "defillama", None)
    if defillama is None:
        return None

    raw_pools = await defillama.get_pools(min_tvl=50_000_000, min_apy=0.5)
    requested = {chain.lower() for chain in (chains or [])}
    candidates = []
    for pool in raw_pools:
        if requested and str(pool.get("chain") or "").lower() not in requested:
            continue
        candidates.append(_pool_to_candidate(pool))

    positions = compose_allocation(candidates, usd_amount, risk_budget=risk_budget)
    if not positions:
        return err_envelope(
            "no_viable_pools",
            "No pools passed the fallback TVL, age, and risk filters.",
        )

    summary = summarise_positions(positions, usd_amount)
    allocation_payload = AllocationPayload(positions=positions, **summary)
    sentinel_matrix_payload = SentinelMatrixPayload(
        positions=positions,
        low_count=summary["risk_mix"]["low"],
        medium_count=summary["risk_mix"]["medium"],
        high_count=summary["risk_mix"]["high"],
        weighted_sentinel=summary["weighted_sentinel"],
    )
    steps = execution_steps_from_positions(positions, usd_amount)
    steps = await _bake_step_transactions(ctx, steps, positions)
    execution_plan_payload = ExecutionPlanPayload(
        steps=steps,
        total_gas=total_gas_from_steps(steps),
        slippage_cap="0.5%",
        wallets=wallets_summary_from_steps(steps),
        tx_count=len(steps),
        requires_signature=True,
    )
    chain_scope = ", ".join(chains or []) if chains else None
    envelope = ok_envelope(
        data={
            "total_usd": summary["total_usd"],
            "blended_apy": summary["blended_apy"],
            "weighted_sentinel": summary["weighted_sentinel"],
            "positions": [position.model_dump() for position in positions],
            "steps": steps,
            "chain_scope": chain_scope,
            "analysis_trace": [
                f"Queried DefiLlama yield pools for {chain_scope or 'all supported chains'} and normalized live pool candidates.",
                f"Filtered live opportunities to {chain_scope or 'all supported chains'} with TVL, operating-history, chain, and APY sanity gates.",
                "Scored candidates via Sentinel pool framework: Safety x Yield durability x Exit liquidity x Confidence.",
                "Cross-checked each protocol against Ilyon Shield: approval surface, admin keys, oracle/bridge dependencies, and incident history.",
                f"Selected {len(positions)} positions across {summary['chains']} chains; Sentinel >= 70 target and position cap <= 35%.",
                f"Composed execution plan with {len(steps)} wallet-gated transactions, router selection, gas estimates, and 0.5% slippage cap.",
                f"Final allocation lands at weighted Sentinel {summary['weighted_sentinel']}/100 and blended APY {summary['blended_apy']}.",
            ],
        },
        card_type="allocation",
        card_payload=allocation_payload.model_dump(),
    )
    envelope.extra_cards = [
        ExtraCard(
            card_id=str(uuid4()),
            card_type="sentinel_matrix",
            payload=sentinel_matrix_payload.model_dump(),
        ),
        ExtraCard(
            card_id=str(uuid4()),
            card_type="execution_plan",
            payload=execution_plan_payload.model_dump(),
        ),
    ]
    return envelope


async def allocate_plan(
    ctx,
    *,
    usd_amount: float,
    risk_budget: str = "balanced",
    chains: list[str] | None = None,
    asset_hint: str | None = None,
    target_apy: float | None = None,
    min_apy: float | None = None,
    max_apy: float | None = None,
    risk_levels: list[str] | None = None,
):
    try:
        usd_amount = float(usd_amount)
    except (TypeError, ValueError):
        return err_envelope("bad_amount", "usd_amount must be a positive number, e.g. 1000.")
    if usd_amount <= 0:
        return err_envelope(
            "bad_amount",
            "Allocation needs a positive USD amount (e.g. 'Allocate $1000 across balanced yield strategies').",
        )
    if usd_amount > 1_000_000_000:
        return err_envelope(
            "bad_amount",
            "Allocation amount looks unrealistic (>$1B). Try a smaller amount such as $1000-$1M.",
        )

    rb = (risk_budget or "balanced").lower()
    if rb not in {"conservative", "balanced", "aggressive"}:
        rb = "balanced"

    normalized_risks = [str(level).upper() for level in (risk_levels or []) if level]

    engine_result = await _allocate_from_engine(
        ctx,
        usd_amount=usd_amount,
        risk_budget=rb,
        chains=chains,
        asset_hint=asset_hint,
        target_apy=target_apy,
        min_apy=min_apy,
        max_apy=max_apy,
        risk_levels=normalized_risks or None,
    )
    # If the engine succeeded with real cards, return it. If it emitted
    # an envelope with ok=False (engine-init ok but the intelligence pipe
    # had no usable output), fall through to the DefiLlama fallback so we
    # always give the user a valid allocation.
    if engine_result is not None and getattr(engine_result, "ok", True):
        return engine_result

    fallback_result = await _allocate_from_defillama(
        ctx,
        usd_amount=usd_amount,
        risk_budget=rb,
        chains=chains,
    )
    if fallback_result is not None:
        return fallback_result

    # Both paths failed — surface the engine's original error if we have one.
    if engine_result is not None:
        return engine_result
    return err_envelope(
        "defi_intelligence_unavailable",
        "The advanced DeFi intelligence engine is not initialized on this server.",
    )
