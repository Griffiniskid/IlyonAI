"""Wallet-assistant transfer builder wrapper.

Imports the real _build_transfer_transaction from the wallet assistant and
wraps it in a Sentinel ToolEnvelope so the agent runtime can consume it
uniformly.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

from src.agent.tools._assistant_bridge import AssistantError, parse_assistant_json
from src.api.schemas.agent import ToolEnvelope
from src.agent.tools._base import err_envelope, ok_envelope


_CHAIN_ID_MAP = {
    "ethereum": 1,
    "arbitrum": 42161,
    "polygon": 137,
    "bsc": 56,
    "base": 8453,
    "optimism": 10,
    "avalanche": 43114,
}


def _get_build_transfer_transaction():
    """Lazy-import _build_transfer_transaction from the wallet assistant."""
    module_name = "wallet_assistant_crypto_agent"
    if module_name in sys.modules:
        return sys.modules[module_name]._build_transfer_transaction

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
    return mod._build_transfer_transaction


async def build_transfer_tx(
    ctx,
    *,
    to_addr: str,
    amount: str,
    chain: str = "ethereum",
    from_addr: str | None = None,
    chain_id: int | None = None,
    token: str | None = None,
):
    """Build a transfer transaction via the wallet assistant.

    Parameters
    ----------
    ctx : ToolCtx
        Agent tool context.
    to_addr : str
        Recipient wallet address.
    amount : str
        Amount to send (in token units).
    chain : str, optional
        Chain name (default "ethereum"). Used to derive chain_id if omitted.
    from_addr : str, optional
        Sender wallet address. Defaults to ctx.wallet.
    chain_id : int, optional
        Explicit chain ID. If omitted, derived from `chain`.
    token : str, optional
        Token symbol (e.g. "USDC"). Defaults to native asset.

    Returns
    -------
    ToolEnvelope
        ok envelope with card_type="transfer" on success,
        err envelope with code="transfer_failed" on error.
    """
    try:
        _build_transfer_transaction = _get_build_transfer_transaction()
    except Exception as exc:
        return err_envelope(
            code="transfer_failed",
            message=f"Failed to import wallet assistant: {exc}",
        )

    if chain_id is None:
        chain_id = _CHAIN_ID_MAP.get(chain.lower(), 56)

    asset = token or "native"
    raw_input = f"send {amount} {asset} to {to_addr}"

    try:
        result_str = await asyncio.to_thread(
            _build_transfer_transaction,
            raw_input,
            chain_id,
        )
    except Exception as exc:
        return err_envelope(
            code="transfer_failed",
            message=f"Wallet assistant error: {exc}",
        )

    try:
        parsed = parse_assistant_json(result_str)
    except AssistantError as exc:
        return err_envelope(
            code="transfer_failed",
            message=str(exc),
        )

    if parsed.get("status") == "error":
        return err_envelope(
            code="transfer_failed",
            message=parsed.get("message", "Unknown transfer error"),
        )

    card_payload = {
        "to": to_addr,
        "amount": parsed.get("amount", amount),
        "chain": chain,
        "token": token,
        "spender": to_addr,
        "steps": [
            {
                "step": 1,
                "action": "transfer",
                "detail": f"Send {amount} {asset} to {to_addr} on {chain}",
            }
        ],
        "requires_signature": True,
    }

    return ok_envelope(
        data=parsed,
        card_type="transfer",
        card_payload=card_payload,
    )
