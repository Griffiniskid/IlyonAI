from typing import Any

from langchain_core.tools import StructuredTool
from src.agent.tools._base import ToolCtx
from src.api.schemas.agent import ToolEnvelope

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

        def _bind(tool_fn, _ctx):
            """Create a wrapper that curries ctx but preserves tool_fn's signature."""

            async def _run(*args, **kwargs):
                # Debug logging
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"TOOL CALL: {tool_fn.__name__} | args: {args} | kwargs: {kwargs}")
                
                # LangChain ReAct agent may pass input as a string containing JSON
                # or as kwargs. Handle both cases.
                result = None
                if args and len(args) == 1:
                    arg = args[0]
                    if isinstance(arg, dict):
                        result = await tool_fn(_ctx, **arg)
                    elif isinstance(arg, str):
                        # Try to parse JSON from the string
                        try:
                            import json
                            # Extract JSON object from string if embedded
                            if '{' in arg and '}' in arg:
                                start = arg.find('{')
                                end = arg.rfind('}') + 1
                                parsed = json.loads(arg[start:end])
                                if isinstance(parsed, dict):
                                    result = await tool_fn(_ctx, **parsed)
                        except (json.JSONDecodeError, ValueError):
                            pass
                        # If can't parse, pass as 'input' parameter
                        if result is None:
                            result = await tool_fn(_ctx, input=arg)
                elif args:
                    result = await tool_fn(_ctx, *args, **kwargs)
                else:
                    result = await tool_fn(_ctx, **kwargs)

                from src.api.schemas.agent import ToolEnvelope
                from src.agent.tools.sentinel_wrap import enrich_tool_envelope

                if isinstance(result, ToolEnvelope):
                    return enrich_tool_envelope(tool_fn.__name__, result)
                return result

            _run.__signature__ = _strip_ctx_param(tool_fn)
            _run.__name__ = tool_fn.__name__
            _run.__doc__ = tool_fn.__doc__
            # langchain's `create_schema_from_function` calls
            # typing.get_type_hints() which reads __annotations__, not the
            # synthetic __signature__ above. Copy annotations from the real
            # tool function so required kwargs (e.g. usd_amount) resolve.
            annotations = dict(getattr(tool_fn, "__annotations__", {}))
            annotations.pop("ctx", None)
            annotations.pop("return", None)
            _run.__annotations__ = annotations
            return _run

        tools.append(
            StructuredTool.from_function(
                coroutine=_bind(fn, ctx),
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
