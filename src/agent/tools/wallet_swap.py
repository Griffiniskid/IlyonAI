"""Wallet-assistant swap builder wrapper.

Imports the real _build_swap_tx from the wallet assistant and wraps it in a
Sentinel ToolEnvelope so the agent runtime can consume it uniformly.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from src.agent.tools._assistant_bridge import AssistantError, parse_assistant_json
from src.agent.tools._base import err_envelope, ok_envelope


def _get_build_swap_tx():
    """Lazy-import _build_swap_tx from the wallet assistant."""
    module_name = "wallet_assistant_crypto_agent"
    if module_name in sys.modules:
        return sys.modules[module_name]._build_swap_tx

    worktree_root = Path(__file__).resolve().parents[3]
    assistant_dir = worktree_root / "IlyonAi-Wallet-assistant-main"
    file_path = assistant_dir / "server" / "app" / "agents" / "crypto_agent.py"
    server_path = assistant_dir / "server"

    if str(server_path) not in sys.path:
        sys.path.insert(0, str(server_path))

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod._build_swap_tx


async def build_swap_tx(
    ctx, *, chain_id, token_in, token_out, amount_in, from_addr
):
    """Build a swap transaction via the wallet assistant.

    Parameters
    ----------
    ctx : ToolCtx
        Agent tool context.
    chain_id : int
        Target chain ID (e.g. 56 for BSC, 101 for Solana).
    token_in : str
        Input token symbol or address.
    token_out : str
        Output token symbol or address.
    amount_in : str
        Input amount in base units (wei for EVM, lamports for Solana).
    from_addr : str
        Sender wallet address.

    Returns
    -------
    ToolEnvelope
        ok envelope with card_type="swap_quote" on success,
        err envelope with code="swap_failed" on error.
    """
    try:
        _build_swap_tx = _get_build_swap_tx()
    except Exception as exc:
        return err_envelope(
            code="swap_failed",
            message=f"Failed to import wallet assistant: {exc}",
        )

    chain = "solana" if chain_id == 101 else "evm"
    slippage_bps = 50 if chain == "solana" else 100

    params = {
        "chain": chain,
        "token_in": token_in,
        "token_out": token_out,
        "amount": amount_in,
        "from": from_addr,
        "chain_id": chain_id,
        "slippage_bps": slippage_bps,
    }
    raw_input = json.dumps(params)

    try:
        result_str = await asyncio.to_thread(_build_swap_tx, raw_input, from_addr, chain_id)
    except Exception as exc:
        return err_envelope(
            code="swap_failed",
            message=f"Wallet assistant error: {exc}",
        )

    try:
        parsed = parse_assistant_json(result_str)
    except AssistantError as exc:
        return err_envelope(
            code="swap_failed",
            message=f"Failed to parse assistant response: {exc}",
        )

    if parsed.get("status") == "error":
        return err_envelope(
            code="swap_failed",
            message=parsed.get("message", "Unknown swap error"),
        )

    chain_type = parsed.get("chain_type", "evm")
    router = "jupiter" if chain_type == "solana" else "enso"

    tx = parsed.get("tx", {})
    if chain_type == "solana":
        spender = parsed.get("fee_account", "")
    else:
        spender = tx.get("to", "")

    amount_in_display = parsed.get("amount_in_display", 0)
    dst_amount_display = parsed.get("dst_amount_display", 0)
    if amount_in_display and dst_amount_display:
        rate = str(round(dst_amount_display / amount_in_display, 8))
    else:
        rate = "0"

    price_impact_raw = parsed.get("price_impact_pct", 0)
    try:
        price_impact_pct = float(price_impact_raw)
    except (TypeError, ValueError):
        price_impact_pct = 0.0

    card_payload = {
        "pay": {"address": token_in, "symbol": parsed.get("from_token_symbol", token_in)},
        "receive": {"address": token_out, "symbol": parsed.get("to_token_symbol", token_out)},
        "rate": rate,
        "router": router,
        "price_impact_pct": price_impact_pct,
        "slippage_bps": slippage_bps,
        "spender": spender,
    }

    return ok_envelope(
        data=parsed,
        card_type="swap_quote",
        card_payload=card_payload,
    )
