from langchain_core.tools import StructuredTool
from src.agent.tools._base import ToolCtx

from .balance import get_wallet_balance
from .price import get_token_price
from .swap_simulate import simulate_swap
from .swap_build import build_swap_tx
from .solana_swap import build_solana_swap
from .market_overview import get_defi_market_overview
from .analytics import get_defi_analytics
from .staking import get_staking_options
from .dex_search import search_dexscreener_pairs
from .pool_find import find_liquidity_pool
from .stake_build import build_stake_tx
from .lp_build import build_deposit_lp_tx
from .bridge_build import build_bridge_tx
from .transfer_build import build_transfer_tx

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
}


def register_all_tools(services, user_id=0, wallet=None):
    ctx = ToolCtx(services=services, user_id=user_id, wallet=wallet)
    tools = []
    for name, (fn, desc) in _TOOL_REGISTRY.items():

        def _bind(tool_fn, _ctx):
            """Create a wrapper that curries ctx but preserves tool_fn's signature."""

            async def _run(*args, **kwargs):
                return await tool_fn(_ctx, *args, **kwargs)

            _run.__signature__ = _strip_ctx_param(tool_fn)
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
