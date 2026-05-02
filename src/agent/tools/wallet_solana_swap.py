"""Sentinel-scored wrapper around crypto_agent.build_solana_swap."""
from __future__ import annotations

from src.agent.tools._assistant_bridge import AssistantError, parse_assistant_json
from src.api.schemas.agent import ToolEnvelope
from src.agent.tools._base import ToolCtx, err_envelope, ok_envelope


async def build_solana_swap(
    ctx: ToolCtx,
    *,
    token_in: str,
    token_out: str,
    amount_in: str,
    from_addr: str,
) -> "ToolEnvelope":  # type: ignore[name-defined]
    from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
        build_solana_swap as _real_build_solana_swap,
    )

    raw_input = f"swap {amount_in} {token_in} to {token_out} for {from_addr}"
    raw = _real_build_solana_swap(raw_input)
    try:
        parsed = parse_assistant_json(raw)
    except AssistantError as exc:
        return err_envelope("solana_swap_failed", str(exc))

    card_payload = {
        "pay": parsed.get("pay") or {"symbol": token_in, "amount": amount_in},
        "receive": parsed.get("receive") or {"symbol": token_out},
        "rate": parsed.get("rate"),
        "router": "Jupiter",
        "price_impact_pct": parsed.get("price_impact_pct"),
        "slippage_bps": parsed.get("slippage_bps"),
        "spender": "Jupiter",
        "chain": "solana",
    }
    return ok_envelope(data=parsed, card_type="swap_quote", card_payload=card_payload)
