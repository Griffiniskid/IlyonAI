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

    sol_wallet = (getattr(ctx, "solana_wallet", "") or "").split(",")[0].strip()
    evm_wallet = (getattr(ctx, "evm_wallet", "") or "").split(",")[0].strip()
    primary = (getattr(ctx, "wallet", "") or "").split(",")[0].strip()
    # If primary looks like an EVM hex address but evm_wallet is empty, promote it.
    if not evm_wallet and primary.lower().startswith("0x") and len(primary) == 42:
        evm_wallet = primary
    # If primary looks like a Solana base58 address but sol_wallet is empty, promote it.
    if not sol_wallet and primary and not primary.lower().startswith("0x"):
        sol_wallet = primary
    # Solana = chain_id 101 (deBridge canonical) or 7565164 (deBridge enum). Either
    # way, source-Solana bridges must sign from the Solana wallet, not the EVM one.
    is_solana_source = src_chain_id in (101, 7565164)
    if not from_addr:
        from_addr = sol_wallet if is_solana_source else (evm_wallet or primary)
    if not from_addr:
        return err_envelope(
            code="bridge_failed",
            message=f"No {'Solana' if is_solana_source else 'EVM'} wallet connected — connect a wallet then retry the bridge.",
        )

    # ── "bridge all/half/25% X" path ─────────────────────────────────────
    pct_factor = None
    amt_str = amount.strip().upper() if isinstance(amount, str) else ""
    if amt_str in ("ALL", "MAX", "ENTIRE", "EVERYTHING", "100%"):
        pct_factor = 1.0
    elif amt_str.startswith("PCT:"):
        try:
            pct_factor = max(0.0, min(1.0, int(amt_str[4:]) / 100.0))
        except ValueError:
            pct_factor = None
    if pct_factor is not None:
        try:
            from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
                get_smart_wallet_balance,
            )
        except Exception as exc:
            return err_envelope(code="bridge_failed", message=f"Balance lookup unavailable: {exc}")
        scan_addr = sol_wallet if is_solana_source else (evm_wallet or primary)
        if not scan_addr:
            return err_envelope(
                code="bridge_failed",
                message=f"Connect a {'Solana' if is_solana_source else 'EVM'} wallet so I can read your {token_in} balance.",
            )
        raw_balance = await asyncio.to_thread(
            get_smart_wallet_balance,
            scan_addr,
            evm_wallet or primary,
            sol_wallet,
        )
        try:
            balance_doc = json.loads(raw_balance) if isinstance(raw_balance, str) else (raw_balance or {})
        except Exception:
            balance_doc = {}
        sym_target = str(token_in).upper()
        matched_amount = None
        matched_decimals = None
        for entry in (balance_doc.get("balances") or []):
            native_sym = str(entry.get("native_symbol") or "").upper()
            if native_sym == sym_target:
                matched_amount = float(entry.get("native_balance") or 0)
                matched_decimals = 9 if entry.get("chain") == "Solana" else 18
                break
            for tok in (entry.get("tokens") or []):
                if str(tok.get("symbol") or "").upper() == sym_target:
                    matched_amount = float(tok.get("balance") or 0)
                    matched_decimals = int(tok.get("decimals") or 0) or None
                    break
            if matched_amount is not None:
                break
        if matched_amount is None or matched_amount <= 0:
            return err_envelope(
                code="bridge_failed",
                message=f"No {sym_target} balance found in your {('Solana' if is_solana_source else 'EVM')} wallet.",
            )
        if not matched_decimals:
            if is_solana_source:
                _SOL_DEC_FALLBACK = {"SOL": 9, "USDC": 6, "USDT": 6}
                matched_decimals = _SOL_DEC_FALLBACK.get(sym_target, 6)
            else:
                _EVM_DEC_FALLBACK = {"USDC": 6, "USDT": 6, "DAI": 18, "WBTC": 8}
                matched_decimals = _EVM_DEC_FALLBACK.get(sym_target, 18)
        # Apply percent factor (half/quarter/etc).
        matched_amount = matched_amount * pct_factor
        # Reserve native gas only when bridging the full balance.
        if pct_factor >= 0.99 and (
            (is_solana_source and sym_target == "SOL")
            or (not is_solana_source and sym_target in {"BNB", "ETH", "MATIC", "AVAX"})
        ):
            matched_amount = max(0.0, matched_amount - 0.005)
            if matched_amount <= 0:
                return err_envelope(
                    code="bridge_failed",
                    message=f"Native {sym_target} balance too small after gas reserve.",
                )
        if matched_amount <= 0:
            return err_envelope(
                code="bridge_failed",
                message=f"Computed {sym_target} amount is zero after applying percent.",
            )
        amount = str(int(matched_amount * (10 ** matched_decimals)))

    params = {
        "token_in": token_in,
        "token_out": token_out,
        "amount": amount,
        "src_chain_id": src_chain_id,
        "dst_chain_id": dst_chain_id,
    }
    raw_input = json.dumps(params)

    # _build_bridge_tx signature: (raw, user_address, default_chain_id, solana_address="").
    # The destination resolver inside picks recipient = sol_wallet or evm_wallet based
    # on dst_chain. Pass both wallets so cross-chain bridges (Solana ↔ EVM) succeed.
    user_addr = evm_wallet or (from_addr if not is_solana_source else "")
    sol_addr = sol_wallet or (from_addr if is_solana_source else "")
    try:
        result_str = await asyncio.to_thread(_build_bridge_tx, raw_input, user_addr, src_chain_id, sol_addr)
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

    # Separate user-requested amount from operating expense.
    # Wallet assistant returns:
    #   - amount_in_display: total source-chain spend (requested + operating expense)
    #   - requested_amount_display: what the user actually asked for
    # Sentinel card surfaces the requested amount in the From column and the
    # operating expense in a dedicated Fee column so the tester is not
    # confused about why "bridge 0.15 SOL" charges 0.16 SOL on Phantom.
    requested = parsed.get("requested_amount_display")
    total_in = parsed.get("amount_in_display")
    op_expense = None
    try:
        if requested is not None and total_in is not None:
            diff = float(total_in) - float(requested)
            if diff > 0.000001:
                op_expense = round(diff, 8)
    except (TypeError, ValueError):
        op_expense = None

    card_payload = {
        "src_chain_id": parsed.get("src_chain_id"),
        "dst_chain_id": parsed.get("dst_chain_id"),
        "amount_in": requested if requested is not None else total_in,
        "amount_in_total": total_in,
        "operating_expense": op_expense,
        "estimated_fee_display": parsed.get("estimated_fee_display"),
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
