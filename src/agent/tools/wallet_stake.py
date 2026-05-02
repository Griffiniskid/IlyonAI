"""Wallet-assistant stake builder wrapper.

Imports the real _build_stake_tx from the wallet assistant and wraps it in a
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


def _get_build_stake_tx():
    """Lazy-import _build_stake_tx from the wallet assistant."""
    module_name = "wallet_assistant_crypto_agent"
    if module_name in sys.modules:
        return sys.modules[module_name]._build_stake_tx

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
    return mod._build_stake_tx


async def build_stake_tx(
    ctx,
    *,
    protocol,
    amount,
    user_addr,
    chain_id=1,
    asset=None,
):
    """Build a stake transaction via the wallet assistant.

    Parameters
    ----------
    ctx : ToolCtx
        Agent tool context.
    protocol : str
        Staking protocol name (e.g. "lido", "rocketpool").
    amount : str
        Amount to stake (in base units or "all").
    user_addr : str
        User wallet address.
    chain_id : int, optional
        Target chain ID (default 1 for Ethereum).
    asset : str, optional
        Asset symbol to stake (e.g. "ETH", "BNB").

    Returns
    -------
    ToolEnvelope
        ok envelope with card_type="stake" on success,
        err envelope with code="stake_failed" on error.
    """
    try:
        _build_stake_tx = _get_build_stake_tx()
    except Exception as exc:
        return err_envelope(
            code="stake_failed",
            message=f"Failed to import wallet assistant: {exc}",
        )

    asset_label = asset or ""
    params = {
        "token": asset_label,
        "protocol": protocol,
        "amount": amount,
        "chain_id": chain_id,
    }
    raw_input = json.dumps(params)

    solana_address = getattr(ctx, "solana_wallet", "") or ""

    try:
        result_str = await asyncio.to_thread(
            _build_stake_tx,
            raw_input,
            user_addr,
            chain_id,
            solana_address,
        )
    except Exception as exc:
        return err_envelope(
            code="stake_failed",
            message=f"Wallet assistant error: {exc}",
        )

    try:
        parsed = parse_assistant_json(result_str)
    except AssistantError as exc:
        return err_envelope(
            code="stake_failed",
            message=f"Failed to parse assistant response: {exc}",
        )

    if parsed.get("status") == "error":
        return err_envelope(
            code="stake_failed",
            message=parsed.get("message", "Unknown stake error"),
        )

    card_payload = {
        "protocol": parsed.get("protocol", protocol),
        "asset": parsed.get("asset", asset_label or "?"),
        "amount": parsed.get("amount", amount),
        "spender": parsed.get("spender") or parsed.get("protocol", protocol),
        "steps": [
            {
                "step": 1,
                "action": "stake",
                "detail": f"Stake {amount} on {parsed.get('protocol', protocol)}",
            }
        ],
        "requires_signature": True,
    }

    return ok_envelope(
        data=parsed,
        card_type="stake",
        card_payload=card_payload,
    )
