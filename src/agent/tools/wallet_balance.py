"""Sentinel-scored wrapper around crypto_agent.get_smart_wallet_balance."""
from __future__ import annotations

from typing import Any

from src.agent.tools._assistant_bridge import AssistantError, parse_assistant_json
from src.api.schemas.agent import ToolEnvelope
from src.agent.tools._base import ToolCtx, err_envelope, ok_envelope


def _flatten_balances(parsed: dict[str, Any]) -> tuple[list[dict], dict[str, dict]]:
    """Convert crypto_agent balance_report into flat tokens[] + by_chain{}.

    Provider shape:
      {balances: [{chain, native_symbol, native_balance, native_usd,
                   tokens: [{symbol, balance, usd_value, ...}], usd_total}, ...]}
    Card consumer expects:
      tokens: [{chain, symbol, amount, usd, mint?}, ...]
      by_chain: {<chain>: {usd, native_symbol, native_amount, native_usd, token_count}}
    """
    if not isinstance(parsed, dict):
        return [], {}

    tokens_out: list[dict] = []
    by_chain: dict[str, dict] = {}

    for entry in parsed.get("balances") or []:
        chain = entry.get("chain") or entry.get("chainName") or "Unknown"
        native_sym = entry.get("native_symbol") or ""
        native_bal = entry.get("native_balance") or 0
        native_usd = entry.get("native_usd") or 0
        chain_total = entry.get("usd_total") or 0
        chain_tokens = entry.get("tokens") or []

        if native_sym and (native_bal or native_usd):
            tokens_out.append({
                "chain": chain,
                "symbol": native_sym,
                "amount": float(native_bal or 0),
                "usd": float(native_usd or 0),
                "is_native": True,
            })

        for t in chain_tokens:
            sym = t.get("symbol") or t.get("ticker") or ""
            amt = t.get("balance") if "balance" in t else t.get("amount", 0)
            usd = t.get("usd_value") if "usd_value" in t else t.get("usd", 0)
            tokens_out.append({
                "chain": chain,
                "symbol": sym,
                "amount": float(amt or 0),
                "usd": float(usd or 0),
                "mint": t.get("mint") or t.get("address"),
                "is_native": False,
            })

        by_chain[chain] = {
            "usd": float(chain_total or 0),
            "native_symbol": native_sym,
            "native_amount": float(native_bal or 0),
            "native_usd": float(native_usd or 0),
            "token_count": len(chain_tokens),
        }

    # Sort tokens descending by USD so the card UI shows biggest first.
    tokens_out.sort(key=lambda t: t.get("usd", 0), reverse=True)
    return tokens_out, by_chain


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

    tokens, by_chain = _flatten_balances(parsed)
    if not tokens:
        tokens = parsed.get("tokens") or []
    if not by_chain:
        by_chain = parsed.get("by_chain") or parsed.get("chains") or {}

    card_payload = {
        "address": addr,
        "total_usd": parsed.get("total_usd"),
        "by_chain": by_chain,
        "tokens": tokens,
        "positions": parsed.get("positions") or [],
    }
    return ok_envelope(data=parsed, card_type="balance", card_payload=card_payload)
