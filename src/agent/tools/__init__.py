import asyncio
from typing import Any

from langchain_core.tools import StructuredTool
from src.agent.tools._base import ToolCtx, err_envelope
from src.api.schemas.agent import ToolEnvelope


# ── RC16: per-tool SLO timeouts ──────────────────────────────────────────────
#
# Pass A surfaced 17.5% of G-category turns (and multiple F/H/I/enso turns)
# hanging in `build_yield_execution_plan` with a 90s curl timeout. The root
# cause: no top-level timeout around tool dispatch — when an upstream RPC /
# Enso / DefiLlama call hangs, the entire SSE stream hangs with it, the
# client times out at 90s, and the agent emits a fabricated card from
# partial state (a financial-loss vector).
#
# This dict sizes each tool's wall-clock budget to its real SLO. When the
# timer fires, the wrapper returns a TOOL_TIMEOUT err_envelope so the
# runtime can surface a blocker card — NEVER fabricate from incomplete data.
_TOOL_SLO_SECONDS: dict[str, float] = {
    # Heavy build / compose / route paths (RC16 explicit defaults).
    "search_defi_opportunities": 30.0,
    "build_yield_execution_plan": 45.0,
    "build_swap_tx": 45.0,                # Enso shortcut route SLO
    "build_solana_swap": 45.0,            # Jupiter route SLO
    "build_bridge_tx": 30.0,              # deBridge order SLO
    "build_deposit_lp_tx": 45.0,
    "build_stake_tx": 30.0,
    "build_transfer_tx": 15.0,
    "compose_plan": 60.0,                 # composed_plan orchestrator SLO
    "allocate_plan": 120.0,               # invokes build_yield_execution_plan N times — multi-pool ops with sentinel scoring + per-pool plan synth routinely take 60-90s with 4+ positions on Solana. Bumped from 60s after BUG-RC regression on R01 multi-pool '40 USDT on sol' where the 60s SLO tripped TOOL_TIMEOUT before the allocation card could emit (the inner allocate_plan call returned ok=True at ~70s).
    "rebalance_portfolio": 120.0,         # same N-pool synthesis pattern as allocate_plan
    "execute_pool_position": 45.0,
    # Quote / read-only paths (smaller budgets).
    "simulate_swap": 20.0,
    "get_token_price": 15.0,
    "get_wallet_balance": 15.0,
    "find_liquidity_pool": 20.0,
    "search_dexscreener_pairs": 15.0,
    "get_defi_market_overview": 20.0,
    "get_defi_analytics": 30.0,
    "get_staking_options": 20.0,
    "analyze_dex_pair": 30.0,
    "analyze_token_full_sentinel": 30.0,
    "analyze_pool_full_sentinel": 30.0,
    "get_smart_money_hub": 30.0,
    "get_shield_check": 30.0,
    "lookup_entity": 15.0,
    "track_whales": 30.0,
    "update_preference": 10.0,
}

# Safety ceiling for any tool not explicitly listed. Chosen so the SSE
# stream still resolves within the 90s client cap with margin for the
# wrap-up event.
_TOOL_SLO_DEFAULT = 45.0


def _slo_for(tool_name: str) -> float:
    return float(_TOOL_SLO_SECONDS.get(tool_name, _TOOL_SLO_DEFAULT))

from .balance import get_wallet_balance
from .price import get_token_price
from .swap_simulate import simulate_swap
from .swap_build import build_swap_tx
from .solana_swap import build_solana_swap
from .market_overview import get_defi_market_overview
from .analytics import get_defi_analytics
from .staking import get_staking_options
from .search_defi_opportunities import search_defi_opportunities
from .dex_search import search_dexscreener_pairs
from .pool_find import find_liquidity_pool
from .stake_build import build_stake_tx
from .lp_build import build_deposit_lp_tx
from .bridge_build import build_bridge_tx
from .transfer_build import build_transfer_tx
from .allocate_plan import allocate_plan
from .build_yield_execution_plan import build_yield_execution_plan
from .execute_pool_position import execute_pool_position
from .analyze_dex_pair import analyze_dex_pair
from .sentinel_features import (
    analyze_pool as analyze_pool_full_sentinel,
    analyze_token_full_sentinel,
    get_shield_check,
    get_smart_money_hub,
    lookup_entity,
    track_whales,
)
from .update_preference import update_preference
from .compose_plan import compose_plan
from .rebalance_portfolio import rebalance_portfolio

_TOOL_REGISTRY = {
    "get_wallet_balance": (get_wallet_balance, "Get multi-chain wallet balance."),
    "get_token_price": (get_token_price, "Get current price for a token."),
    "simulate_swap": (simulate_swap, "Quote a swap (no tx build)."),
    "build_swap_tx": (build_swap_tx, "Build an unsigned EVM swap tx via Enso."),
    "build_solana_swap": (
        build_solana_swap,
        "Build an unsigned Solana swap tx via Jupiter.",
    ),
    "get_defi_market_overview": (
        get_defi_market_overview,
        "Aggregate DeFi market stats.",
    ),
    "get_defi_analytics": (
        get_defi_analytics,
        "Tiered pool/protocol analytics.",
    ),
    "get_staking_options": (
        get_staking_options,
        "List liquid-staking and staking options.",
    ),
    "search_defi_opportunities": (
        search_defi_opportunities,
        (
            "Constraint-aware DeFi opportunity search. Use for pool, farm, vault, lending, "
            "or APY requests where user specifies risk, APY target, chain, search/research, "
            "or execution readiness. Returns matched candidates, excluded reasons, source trace, "
            "and blockers when execution is requested but no verified adapter exists."
        ),
    ),
    "search_dexscreener_pairs": (
        search_dexscreener_pairs,
        "Search DexScreener pairs.",
    ),
    "find_liquidity_pool": (
        find_liquidity_pool,
        "Find a liquidity pool for a pair.",
    ),
    "build_stake_tx": (build_stake_tx, "Build an unsigned stake tx."),
    "build_deposit_lp_tx": (
        build_deposit_lp_tx,
        "Build an unsigned LP deposit tx.",
    ),
    "build_bridge_tx": (
        build_bridge_tx,
        "Build an unsigned deBridge transfer.",
    ),
    "build_transfer_tx": (
        build_transfer_tx,
        "Build an unsigned native transfer.",
    ),
    "allocate_plan": (
        allocate_plan,
        (
            "ONE-SHOT allocation planner. Call exactly once when the user asks "
            "to 'allocate', 'distribute', 'diversify', or 'deploy' a specific "
            "USD amount across yield / staking. Args: usd_amount (float, required), "
            "risk_budget ('conservative'|'balanced'|'aggressive', default 'balanced'), "
            "chains (optional list). Returns ranked top-5 positions, Sentinel "
            "matrix, and an execution plan — in one call. Do NOT follow up with "
            "other tools for an allocation intent."
        ),
    ),
    "update_preference": (
        update_preference,
        (
            "Persist user preferences across sessions. Call when the user says "
            "'set my slippage to 30 bps', 'use only Arbitrum and Base', "
            "'low-risk only', etc. Allowed kwargs: risk_budget "
            "('conservative'|'balanced'|'aggressive'), preferred_chains (list), "
            "blocked_protocols (list), gas_cap_usd, slippage_cap_bps, "
            "notional_double_confirm_usd, auto_rebalance_opt_in (0|1)."
        ),
    ),
    "compose_plan": (
        compose_plan,
        (
            "Validate a multi-step intent DAG and return an execution plan card. "
            "Call when the user wants to perform multiple actions in sequence "
            "(e.g., 'bridge then swap then stake'). Args: intent (dict) with "
            "'title' and 'steps' list. Each step needs 'action' and 'params'. "
            "Returns an execution_plan_v2 card with ordered steps, gas estimates, "
            "dependency graph, and Sentinel risk assessment."
        ),
    ),
    "rebalance_portfolio": (
        rebalance_portfolio,
        (
            "Propose an optimal rebalance plan based on your current holdings. "
            "Call when the user says 'rebalance my portfolio' or similar. "
            "Respects the user's risk_budget, preferred_chains, and blocked_protocols "
            "from agent_preferences. Returns an ExecutionPlanV2Card."
        ),
    ),
    "build_yield_execution_plan": (
        build_yield_execution_plan,
        (
            "Build a real ExecutionPlanV3 (approve + supply / deposit) for a specific "
            "yield protocol via the adapter registry. Call when the user wants to "
            "execute a specific yield action like 'supply 100 USDC to Aave V3'. Args: "
            "chain, protocol, action ('supply'|'deposit_lp'|'stake'), asset_in, "
            "amount_in, optional asset_out, slippage_bps, inventory."
        ),
    ),
    "analyze_dex_pair": (
        analyze_dex_pair,
        (
            "Auto-detect a pasted address: if it's a DexScreener pair, run pool "
            "analysis; if it's a token mint, run token analysis. Use whenever "
            "the user pastes a 32-44 base58 Solana address or a 0x… EVM address "
            "with phrasings like 'analyze this pair', 'what is this pool', "
            "'check this pool address', 'analyze this on dexscreener'. Args: "
            "address, optional chain."
        ),
    ),
    "execute_pool_position": (
        execute_pool_position,
        (
            "ONE-CLICK pool deposit. Call when the user says 'execute this pool', "
            "'execute raydium-amm SPACEX-WSOL', 'deposit into pool X', or pastes a "
            "DefiLlama pool URL/UUID. Resolves the pool's chain, protocol, asset, and "
            "LP mint via DefiLlama, then builds a real ExecutionPlanV3 the user signs "
            "in Phantom or MetaMask — same flow as build_swap_tx and build_bridge_tx. "
            "Args: pool (UUID or 'protocol pair'), amount, optional asset_in, "
            "optional slippage_bps. Use AFTER allocate_plan or "
            "search_defi_opportunities when the user wants to actually deposit."
        ),
    ),
    "analyze_token_full_sentinel": (
        analyze_token_full_sentinel,
        (
            "FULL Sentinel token analysis (rugcheck + holders + liquidity + AI score). "
            "Call when the user says 'analyze token X', pastes a Solana mint or 0x "
            "contract, or asks 'is X safe / a rug / overvalued'. Args: address, "
            "optional chain ('solana','ethereum','bsc',...), mode ('quick'|'standard'|'deep')."
        ),
    ),
    "track_whales": (
        track_whales,
        (
            "Recent whale transactions across supported chains. Call on 'show me whales', "
            "'whale activity in last 6h', 'big buyers of X'. Args: optional chain, hours (default 24), limit."
        ),
    ),
    "get_smart_money_hub": (
        get_smart_money_hub,
        (
            "Smart-money hub for a chain (top wallets, accumulations, conviction picks). "
            "Default chain: solana. Call on 'smart money', 'top traders', 'conviction picks'. "
            "Args: chain (default 'solana'), limit."
        ),
    ),
    "get_shield_check": (
        get_shield_check,
        (
            "Sentinel Shield risk scan for a wallet or contract. Call on 'shield this address', "
            "'is this contract safe', 'check approvals'. Args: address, optional chain."
        ),
    ),
    "lookup_entity": (
        lookup_entity,
        (
            "Resolve a name/ENS/address/fund tag to a Sentinel entity profile. Call on "
            "'who is X', 'find entity Y', 'is this address tagged'. Args: query."
        ),
    ),
    "analyze_pool_full_sentinel": (
        analyze_pool_full_sentinel,
        (
            "Sentinel-grade pool analysis (APY, TVL, IL risk, DefiLlama outlook). Call on "
            "'analyze pool X', 'is raydium-amm SPACEX-WSOL safe', 'show pool stats'. Args: "
            "pool (UUID or 'protocol pair'), optional chain."
        ),
    ),
}


def register_all_tools(services, user_id=0, wallet=None, solana_wallet=None, evm_wallet=None):
    ctx = ToolCtx(
        services=services,
        user_id=user_id,
        wallet=wallet,
        solana_wallet=solana_wallet,
        evm_wallet=evm_wallet,
    )
    tools = []
    for name, (fn, desc) in _TOOL_REGISTRY.items():

        # IMPORTANT: re-resolve the tool function from the registry on every
        # call so `monkeypatch.setitem(_TOOL_REGISTRY, "<name>", (stub, ...))`
        # in tests is honoured — and so the SLO is looked up by the registered
        # name (dict key), not the function's `__name__` (which a stub may
        # have changed). Without this, a monkeypatched slow stub would carry
        # a different `__name__` (e.g. ``_slow_get_token_price``) and silently
        # fall back to the default 45s SLO, letting hung tools slip past the
        # dispatcher timeout — the exact RC16 financial-loss vector.
        def _resolve(_name=name):
            entry = _TOOL_REGISTRY.get(_name)
            if entry is None:
                return None
            return entry[0]

        def _late_bound(_ctx, _name=name):
            async def _run(*args, **kwargs):
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"TOOL CALL: {_name} | args: {args} | kwargs: {kwargs}")

                tool_fn = _resolve(_name)
                if tool_fn is None:
                    return err_envelope(
                        code="TOOL_MISSING",
                        message=f"Tool '{_name}' was unregistered before dispatch.",
                    )

                _slo = _slo_for(_name)

                async def _invoke() -> Any:
                    if args and len(args) == 1:
                        arg = args[0]
                        if isinstance(arg, dict):
                            return await tool_fn(_ctx, **arg)
                        if isinstance(arg, str):
                            try:
                                import json
                                if '{' in arg and '}' in arg:
                                    start = arg.find('{')
                                    end = arg.rfind('}') + 1
                                    parsed = json.loads(arg[start:end])
                                    if isinstance(parsed, dict):
                                        return await tool_fn(_ctx, **parsed)
                            except (json.JSONDecodeError, ValueError):
                                pass
                            return await tool_fn(_ctx, input=arg)
                    if args:
                        return await tool_fn(_ctx, *args, **kwargs)
                    return await tool_fn(_ctx, **kwargs)

                try:
                    result = await asyncio.wait_for(_invoke(), timeout=_slo)
                except asyncio.TimeoutError:
                    logger.warning(
                        "TOOL_TIMEOUT: %s exceeded SLO %.1fs", _name, _slo
                    )
                    return err_envelope(
                        code="TOOL_TIMEOUT",
                        message=(
                            f"Tool '{_name}' exceeded its {_slo:.0f}s SLO. "
                            f"Upstream call (RPC / Enso / DefiLlama / aggregator) "
                            f"hung — no execution plan emitted. Retry or pick a "
                            f"different route."
                        ),
                    )

                from src.api.schemas.agent import ToolEnvelope
                from src.agent.tools.sentinel_wrap import enrich_tool_envelope

                if isinstance(result, ToolEnvelope):
                    return enrich_tool_envelope(_name, result)
                return result

            _run.__signature__ = _strip_ctx_param(fn)
            _run.__name__ = _name
            _run.__doc__ = fn.__doc__
            annotations = dict(getattr(fn, "__annotations__", {}))
            annotations.pop("ctx", None)
            annotations.pop("return", None)
            _run.__annotations__ = annotations
            return _run

        tools.append(
            StructuredTool.from_function(
                coroutine=_late_bound(ctx),
                name=name,
                description=desc,
            )
        )
    return tools


def _strip_ctx_param(fn):
    """Return an inspect.Signature matching *fn* but without the first (ctx) param."""
    import inspect

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    # Remove the first parameter (ctx: ToolCtx)
    if params:
        params = params[1:]
    return sig.replace(parameters=params)
