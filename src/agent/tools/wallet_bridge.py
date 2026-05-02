"""Wallet-assistant bridge builder wrapper.

Imports the real _build_bridge_tx from the wallet assistant and wraps it in a
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
from src.api.schemas.agent import ToolEnvelope
from src.agent.tools._base import err_envelope, ok_envelope


def _get_build_bridge_tx():
    """Lazy-import _build_bridge_tx from the wallet assistant."""
    module_name = "wallet_assistant_crypto_agent"
    if module_name in sys.modules:
        return sys.modules[module_name]._build_bridge_tx

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
    return mod._build_bridge_tx


async def build_bridge_tx(
    ctx, *, src_chain_id, dst_chain_id, token_in, token_out, amount, from_addr=None
):
    """Build a cross-chain bridge transaction via the wallet assistant.

    Parameters
    ----------
    ctx : ToolCtx
        Agent tool context.
    src_chain_id : int
        Source chain ID (e.g. 56 for BSC, 101 for Solana).
    dst_chain_id : int
        Destination chain ID (e.g. 42161 for Arbitrum, 8453 for Base).
    token_in : str
        Input token symbol or address.
    token_out : str
        Output token symbol or address.
    amount : str
        Bridge amount in smallest units (wei for EVM, lamports for Solana).
    from_addr : str
        Sender wallet address.

    Returns
    -------
    ToolEnvelope
        ok envelope with card_type="bridge" on success,
        err envelope with code="bridge_failed" on error.
    """
    try:
        _build_bridge_tx = _get_build_bridge_tx()
    except Exception as exc:
        return err_envelope(
            code="bridge_failed",
            message=f"Failed to import wallet assistant: {exc}",
        )

    from_addr = from_addr or getattr(ctx, "wallet", None) or ""
    if not from_addr:
        return err_envelope("bridge_failed", "No wallet address provided for bridge transaction.")

    params = {
        "token_in": token_in,
        "token_out": token_out,
        "amount": amount,
        "src_chain_id": src_chain_id,
        "dst_chain_id": dst_chain_id,
    }
    raw_input = json.dumps(params)

    try:
        result_str = await asyncio.to_thread(_build_bridge_tx, raw_input, from_addr, src_chain_id)
    except Exception as exc:
        return err_envelope(
            code="bridge_failed",
            message=f"Wallet assistant error: {exc}",
        )

    try:
        parsed = parse_assistant_json(result_str)
    except AssistantError as exc:
        return err_envelope(
            code="bridge_failed",
            message=f"Failed to parse assistant response: {exc}",
        )

    if parsed.get("status") == "error":
        return err_envelope(
            code="bridge_failed",
            message=parsed.get("message", "Unknown bridge error"),
        )

    tx = parsed.get("tx", {})
    chain_type = parsed.get("chain_type", "evm")
    spender = tx.get("to", "") if chain_type == "evm" else ""

    card_payload = {
        "src_chain_id": parsed.get("src_chain_id"),
        "dst_chain_id": parsed.get("dst_chain_id"),
        "amount_in": parsed.get("amount_in_display"),
        "amount_out": parsed.get("dst_amount_display"),
        "router": "debridge",
        "estimated_seconds": parsed.get("estimated_fill_time_seconds"),
        "spender": spender,
    }

    return ok_envelope(
        data=parsed,
        card_type="bridge",
        card_payload=card_payload,
    )
