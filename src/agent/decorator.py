"""Sentinel + Shield decorator that enriches tool envelopes."""
from __future__ import annotations

from src.api.schemas.agent import ToolEnvelope, SentinelBlock, ShieldBlock

DECORATION_MAP: dict[str, list[str]] = {
    "find_liquidity_pool": ["sentinel"],
    "get_defi_analytics": ["sentinel"],
    "get_staking_options": ["sentinel"],
    "get_token_price": ["shield"],
    "get_wallet_balance": ["shield_all_positions"],
    "simulate_swap": ["shield_both_legs"],
    "build_swap_tx": ["shield_both_legs"],
    "build_solana_swap": ["shield_both_legs"],
    "search_dexscreener_pairs": ["shield_all_pairs"],
    "get_defi_market_overview": [],
    "build_bridge_tx": ["shield_both_legs"],
    "build_stake_tx": ["sentinel"],
    "build_deposit_lp_tx": ["sentinel"],
    "build_transfer_tx": [],
}


async def decorate(tool_name: str, raw: dict | ToolEnvelope, ctx) -> ToolEnvelope:
    """Apply sentinel/shield decorations to a tool envelope."""
    env = ToolEnvelope.model_validate(raw) if isinstance(raw, dict) else raw
    if not env.ok or env.data is None:
        return env
    for strategy in DECORATION_MAP.get(tool_name, []):
        await _apply(strategy, env, ctx)
    return env


async def _apply(strategy: str, env: ToolEnvelope, ctx) -> None:
    """Apply a single decoration strategy (never hard-fails)."""
    try:
        if strategy == "sentinel":
            if hasattr(ctx.services, "opportunity") and ctx.services.opportunity:
                s = await ctx.services.opportunity.summarize(env.data)
                env.sentinel = SentinelBlock(**s)
                if env.card_payload is not None:
                    env.card_payload["sentinel"] = s

        elif strategy == "shield":
            if hasattr(ctx.services, "shield") and ctx.services.shield:
                addr = env.data.get("address") or env.data.get("mint")
                if addr:
                    v = await ctx.services.shield.verdict(addr)
                    env.shield = ShieldBlock(**v)

        elif strategy == "shield_both_legs":
            if hasattr(ctx.services, "shield") and ctx.services.shield:
                for key in ("pay", "receive"):
                    leg = env.data.get(key, {})
                    tok = leg.get("address") or leg.get("mint")
                    if tok and env.card_payload is not None:
                        v = await ctx.services.shield.verdict(tok)
                        env.card_payload[f"{key}_shield"] = v

        elif strategy == "shield_all_positions":
            if hasattr(ctx.services, "shield") and ctx.services.shield:
                for pos in (env.card_payload or {}).get("positions", []):
                    tok = pos.get("address") or pos.get("mint")
                    if tok:
                        pos["shield"] = await ctx.services.shield.verdict(tok)

        elif strategy == "shield_all_pairs":
            if hasattr(ctx.services, "shield") and ctx.services.shield:
                for pair in (env.card_payload or {}).get("pairs", []):
                    tok = pair.get("base_address")
                    if tok:
                        pair["shield"] = await ctx.services.shield.verdict(tok)
    except Exception:
        pass  # decorator never hard-fails
