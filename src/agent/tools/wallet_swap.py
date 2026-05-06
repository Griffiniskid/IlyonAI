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
from src.api.schemas.agent import ToolEnvelope
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
    ctx, *, chain_id, token_in, token_out, amount_in, from_addr=""
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

    # Jupiter's quote API requires real SPL mint addresses, not symbols. Resolve
    # the common ones inline so intent-time routing can pass plain symbols.
    if chain == "solana":
        _SOL_MINT_BY_SYMBOL = {
            "SOL": "So11111111111111111111111111111111111111112",
            "WSOL": "So11111111111111111111111111111111111111112",
            "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
            "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
            "ORCA": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
            "JITOSOL": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
            "MSOL": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
            "STSOL": "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",
        }
        if isinstance(token_in, str) and token_in.upper() in _SOL_MINT_BY_SYMBOL:
            token_in_resolved = _SOL_MINT_BY_SYMBOL[token_in.upper()]
        else:
            token_in_resolved = token_in
        if isinstance(token_out, str) and token_out.upper() in _SOL_MINT_BY_SYMBOL:
            token_out_resolved = _SOL_MINT_BY_SYMBOL[token_out.upper()]
        else:
            token_out_resolved = token_out
    else:
        token_in_resolved = token_in
        token_out_resolved = token_out

    # Fall back to the session wallet so intent-time routing doesn't need to
    # know the connected address. Solana uses ctx.solana_wallet; EVM uses
    # ctx.evm_wallet (with ctx.wallet as a final fallback).
    sol_wallet = (getattr(ctx, "solana_wallet", "") or "").split(",")[0].strip()
    evm_wallet = (getattr(ctx, "evm_wallet", "") or "").split(",")[0].strip()
    primary = (getattr(ctx, "wallet", "") or "").split(",")[0].strip()
    if not from_addr:
        from_addr = sol_wallet if chain == "solana" else (evm_wallet or primary)
    if not from_addr:
        return err_envelope(
            code="swap_failed",
            message=f"No {'Solana' if chain == 'solana' else 'EVM'} wallet connected — connect a wallet then retry the swap.",
        )

    params = {
        "chain": chain,
        "token_in": token_in_resolved,
        "token_out": token_out_resolved,
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

    # Enrich Solana payloads so the legacy SimulationPreview parser shows the
    # real symbols and human-readable amounts. _build_jupiter_swap_tx returns
    # only out_amount + tx.serialized; the front-end parser falls back to "Token"
    # / "—" without these.
    if chain_type == "solana":
        _SOL_DEC = {"SOL": 9, "WSOL": 9, "USDC": 6, "USDT": 6, "BONK": 5,
                    "JUP": 6, "PYTH": 6, "RAY": 6, "ORCA": 6, "JITO": 9,
                    "JITOSOL": 9, "MSOL": 9, "STSOL": 9, "WBTC": 8, "WETH": 8}
        in_sym = str(token_in).upper() if isinstance(token_in, str) else ""
        out_sym = str(token_out).upper() if isinstance(token_out, str) else ""
        in_dec = _SOL_DEC.get(in_sym, 9)
        out_dec = _SOL_DEC.get(out_sym, 9)
        try:
            ui_in = round(int(amount_in) / (10 ** in_dec), 8)
            parsed.setdefault("ui_in_amount", ui_in)
            parsed.setdefault("amount_in_display", ui_in)
        except Exception:
            pass
        try:
            out_amt = parsed.get("out_amount")
            if out_amt is not None:
                ui_out = round(int(out_amt) / (10 ** out_dec), 8)
                parsed.setdefault("ui_out_amount", ui_out)
                parsed.setdefault("dst_amount_display", ui_out)
        except Exception:
            pass
        if in_sym:
            parsed.setdefault("in_symbol", in_sym)
            parsed.setdefault("from_token_symbol", in_sym)
        if out_sym:
            parsed.setdefault("out_symbol", out_sym)
            parsed.setdefault("to_token_symbol", out_sym)
        parsed.setdefault("route_summary", "Jupiter route")
        # Mirror tx.serialized to top-level swapTransaction for legacy parser branches.
        ser = (parsed.get("tx") or {}).get("serialized")
        if ser and "swapTransaction" not in parsed:
            parsed["swapTransaction"] = ser

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
