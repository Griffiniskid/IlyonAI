"""Wallet-assistant LP deposit builder wrapper.

Imports the real _build_deposit_lp_tx from the wallet assistant and wraps it in
a Sentinel ToolEnvelope so the agent runtime can consume it uniformly.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from src.agent.tools._assistant_bridge import AssistantError, parse_assistant_json
from src.agent.tools._base import err_envelope, ok_envelope


def _get_build_deposit_lp_tx():
    """Lazy-import _build_deposit_lp_tx from the wallet assistant."""
    module_name = "wallet_assistant_crypto_agent"
    if module_name in sys.modules:
        return sys.modules[module_name]._build_deposit_lp_tx

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
    return mod._build_deposit_lp_tx


async def build_deposit_lp_tx(
    ctx,
    *,
    protocol,
    token_a,
    token_b,
    amount_a,
    amount_b,
    user_addr,
    chain_id=1,
):
    """Build an LP deposit transaction via the wallet assistant.

    Parameters
    ----------
    ctx : ToolCtx
        Agent tool context.
    protocol : str
        LP protocol name (e.g. "curve", "uniswap_v2").
    token_a : str
        First token symbol of the pair.
    token_b : str
        Second token symbol of the pair.
    amount_a : str
        Amount of token_a to deposit.
    amount_b : str
        Amount of token_b to deposit.
    user_addr : str
        User wallet address.
    chain_id : int, optional
        Target chain ID (default 1 for Ethereum).

    Returns
    -------
    ToolEnvelope
        ok envelope with card_type="lp" on success,
        err envelope with code="lp_failed" on error.
    """
    try:
        _build_deposit_lp_tx_fn = _get_build_deposit_lp_tx()
    except Exception as exc:
        return err_envelope(
            code="lp_failed",
            message=f"Failed to import wallet assistant: {exc}",
        )

    # The wallet assistant's _build_deposit_lp_tx expects JSON input with keys
    # token_in, pool_address, amount, chain_id, protocol. Sentinel's tool API
    # exposes a 2-token signature (token_a/token_b/amount_a/amount_b), so we
    # forward token_a/amount_a as token_in/amount and pass token_b through
    # pool_address (callers should supply the LP token contract there in
    # production; in tests this field is unused by the mock).
    params = {
        "token_in": token_a,
        "pool_address": token_b,
        "amount": amount_a,
        "chain_id": chain_id,
        "protocol": protocol,
        "amount_b": amount_b,
    }
    raw_input = json.dumps(params)

    try:
        result_str = await asyncio.to_thread(
            _build_deposit_lp_tx_fn,
            raw_input,
            user_addr,
            chain_id,
        )
    except Exception as exc:
        return err_envelope(
            code="lp_failed",
            message=f"Wallet assistant error: {exc}",
        )

    try:
        parsed = parse_assistant_json(result_str)
    except AssistantError as exc:
        return err_envelope(
            code="lp_failed",
            message=f"Failed to parse assistant response: {exc}",
        )

    if parsed.get("status") == "error":
        return err_envelope(
            code="lp_failed",
            message=parsed.get("message", "Unknown LP error"),
        )

    resolved_protocol = parsed.get("protocol", protocol)
    card_payload = {
        "protocol": resolved_protocol,
        "pair": f"{token_a}/{token_b}",
        "amount_a": parsed.get("amount_a", amount_a),
        "amount_b": parsed.get("amount_b", amount_b),
        "spender": parsed.get("spender") or resolved_protocol,
        "steps": [
            {
                "step": 1,
                "action": "deposit_lp",
                "detail": (
                    f"Deposit LP {token_a}/{token_b} on {resolved_protocol}"
                ),
            }
        ],
        "requires_signature": True,
    }

    return ok_envelope(
        data=parsed,
        card_type="lp",
        card_payload=card_payload,
    )
