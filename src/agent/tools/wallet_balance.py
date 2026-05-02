"""Sentinel-scored wrapper around crypto_agent.get_smart_wallet_balance."""
from __future__ import annotations

from src.agent.tools._assistant_bridge import AssistantError, parse_assistant_json
from src.api.schemas.agent import ToolEnvelope
from src.agent.tools._base import ToolCtx, err_envelope, ok_envelope


async def get_wallet_balance(
    ctx: ToolCtx,
    *,
    wallet: str | None = None,
) -> "ToolEnvelope":  # type: ignore[name-defined]
    from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
        get_smart_wallet_balance,
    )

    addr = wallet or ctx.wallet
    if not addr:
        return err_envelope("missing_wallet", "No wallet address provided")

    raw = get_smart_wallet_balance(addr, user_address=addr,
                                   solana_address=getattr(ctx, "solana_wallet", "") or "")
    try:
        parsed = parse_assistant_json(raw)
    except AssistantError as exc:
        return err_envelope("balance_failed", str(exc))

    card_payload = {
        "address": addr,
        "total_usd": parsed.get("total_usd"),
        "by_chain": parsed.get("by_chain") or parsed.get("chains") or {},
        "tokens": parsed.get("tokens") or [],
        "positions": parsed.get("positions") or [],
    }
    return ok_envelope(data=parsed, card_type="balance", card_payload=card_payload)
