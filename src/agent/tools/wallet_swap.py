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

from src.agent.intent.validation import (
    is_stop_word,
    is_valid_symbol_shape,
    translate_aggregator_error,
    validate_swap_params,
)
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
    # Pre-flight semantic gate. Catches LLM tool-call mistakes (stop-words as
    # tickers, cross-chain mismatches, garbage amounts) before reaching Enso/
    # Jupiter. Symbols only — pass-through when the caller already supplied
    # an on-chain address (prefix 0x or base58-shaped) since validation only
    # speaks in tickers.
    def _is_address_like(t):
        if not isinstance(t, str):
            return False
        s = t.strip()
        return s.startswith("0x") and len(s) == 42 or len(s) >= 32 and not s.isdecimal()

    if isinstance(token_in, str) and not _is_address_like(token_in):
        if (not is_valid_symbol_shape(token_in)) or is_stop_word(token_in):
            return err_envelope(
                code="invalid_token",
                message=(
                    f"'{token_in}' isn't a valid token symbol. "
                    f"Use a canonical ticker like SOL, USDC, ETH."
                ),
            )
    if isinstance(token_out, str) and not _is_address_like(token_out):
        if (not is_valid_symbol_shape(token_out)) or is_stop_word(token_out):
            return err_envelope(
                code="invalid_token",
                message=(
                    f"'{token_out}' isn't a valid token symbol. "
                    f"Use a canonical ticker like WBNB, USDC, ETH."
                ),
            )

    # When both sides are tickers (not addresses) we can run the full check.
    if (isinstance(token_in, str) and not _is_address_like(token_in)
            and isinstance(token_out, str) and not _is_address_like(token_out)):
        amt_str_check = str(amount_in).strip().upper() if amount_in is not None else ""
        is_sentinel = (
            amt_str_check in ("ALL", "MAX", "ENTIRE", "EVERYTHING", "100%")
            or amt_str_check.startswith("PCT:")
        )
        v = validate_swap_params(
            token_in=token_in,
            token_out=token_out,
            chain_id=int(chain_id) if chain_id is not None else None,
            amount_in=amount_in,
            amount_is_sentinel=is_sentinel,
        )
        if not v.ok:
            return err_envelope(
                code=v.error_code or "swap_failed",
                message=v.user_message or "Swap rejected by validation.",
            )

    try:
        _build_swap_tx = _get_build_swap_tx()
    except Exception as exc:
        return err_envelope(
            code="swap_failed",
            message=f"Failed to import wallet assistant: {exc}",
        )

    chain = "solana" if chain_id == 101 else "evm"
    slippage_bps = 50 if chain == "solana" else 100

    # ── "swap all/half/50% X to Y" path ──────────────────────────────────
    # Sentinel "ALL" / "PCT:NN" means: read the user's current balance for
    # token_in from the wallet scanner, take that fraction, convert to base
    # units, then proceed as a normal numeric swap. Done here (not in the
    # detector) so we have ctx.
    pct_factor = None
    amt_str = amount_in.strip().upper() if isinstance(amount_in, str) else ""
    if amt_str in ("ALL", "MAX", "ENTIRE", "EVERYTHING", "100%"):
        pct_factor = 1.0
    elif amt_str.startswith("PCT:"):
        try:
            pct_factor = max(0.0, min(1.0, int(amt_str[4:]) / 100.0))
        except ValueError:
            pct_factor = None
    if pct_factor is not None:
        sol_wallet_addr = (getattr(ctx, "solana_wallet", "") or "").split(",")[0].strip()
        evm_wallet_addr = (getattr(ctx, "evm_wallet", "") or "").split(",")[0].strip()
        primary_addr = (getattr(ctx, "wallet", "") or "").split(",")[0].strip()
        scan_addr = (sol_wallet_addr if chain == "solana" else evm_wallet_addr) or primary_addr
        if not scan_addr:
            return err_envelope(
                code="swap_failed",
                message=f"Connect a {'Solana' if chain == 'solana' else 'EVM'} wallet so I can read your {token_in} balance.",
            )
        try:
            from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
                get_smart_wallet_balance,
            )
        except Exception as exc:
            return err_envelope(code="swap_failed", message=f"Balance lookup unavailable: {exc}")
        raw_balance = await asyncio.to_thread(
            get_smart_wallet_balance,
            scan_addr,
            evm_wallet_addr or primary_addr,
            sol_wallet_addr,
        )
        try:
            balance_doc = json.loads(raw_balance) if isinstance(raw_balance, str) else (raw_balance or {})
        except Exception:
            balance_doc = {}
        sym_target = str(token_in).upper()
        matched_amount = None
        matched_decimals = None
        matched_mint = None
        for entry in (balance_doc.get("balances") or []):
            native_sym = str(entry.get("native_symbol") or "").upper()
            if native_sym == sym_target:
                matched_amount = float(entry.get("native_balance") or 0)
                # Native decimals: SOL=9, EVM=18.
                matched_decimals = 9 if (entry.get("chain") == "Solana") else 18
                break
            for tok in (entry.get("tokens") or []):
                if str(tok.get("symbol") or "").upper() == sym_target:
                    matched_amount = float(tok.get("balance") or 0)
                    matched_decimals = int(tok.get("decimals") or 0) or None
                    matched_mint = tok.get("mint") or tok.get("address") or None
                    break
            if matched_amount is not None:
                break
        if matched_amount is None or matched_amount <= 0:
            return err_envelope(
                code="swap_failed",
                message=f"No {sym_target} balance found in your wallet.",
            )
        # Decimals fallback by symbol if the scanner didn't return one.
        if not matched_decimals:
            if chain == "solana":
                _SOL_DEC_FALLBACK = {"SOL": 9, "WSOL": 9, "USDC": 6, "USDT": 6, "BONK": 5,
                                     "JUP": 6, "PYTH": 6, "RAY": 6, "ORCA": 6, "JITOSOL": 9,
                                     "MSOL": 9, "STSOL": 9}
                matched_decimals = _SOL_DEC_FALLBACK.get(sym_target, 6)
            else:
                matched_decimals = 18
        # Apply the percent factor — half/quarter/etc.
        matched_amount = matched_amount * pct_factor
        # Leave a small dust buffer on natives so signing doesn't fail on gas
        # (only when sweeping the full balance — partial swaps don't need it).
        if pct_factor >= 0.99 and (
            (chain == "solana" and sym_target == "SOL")
            or (chain == "evm" and sym_target in {"BNB", "ETH", "MATIC", "AVAX"})
        ):
            matched_amount = max(0.0, matched_amount - (0.001 if chain == "solana" else 0.002))
            if matched_amount <= 0:
                return err_envelope(
                    code="swap_failed",
                    message=f"Native {sym_target} balance too small after gas reserve.",
                )
        if matched_amount <= 0:
            return err_envelope(
                code="swap_failed",
                message=f"Computed {sym_target} amount is zero after applying percent.",
            )
        amount_in = str(int(matched_amount * (10 ** matched_decimals)))
        # If the scanner gave us the actual mint address, use it directly so
        # Jupiter doesn't need to symbol-resolve a meme like FATPENGU.
        if chain == "solana" and matched_mint:
            token_in = matched_mint

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
            message=translate_aggregator_error(str(exc)),
        )

    try:
        parsed = parse_assistant_json(result_str)
    except AssistantError as exc:
        return err_envelope(
            code="swap_failed",
            message=f"Failed to parse swap response: {exc}",
        )

    if parsed.get("status") == "error":
        return err_envelope(
            code="swap_failed",
            message=translate_aggregator_error(parsed.get("message", "Unknown swap error")),
        )

    chain_type = parsed.get("chain_type", "evm")
    router = "jupiter" if chain_type == "solana" else "enso"

    # Override "Token" placeholder when token_out is a canonical LST. Enso/Jupiter
    # don't always know the symbol of niche LSTs (slisBNB, jitoSOL, MATICX, sAVAX),
    # so the chat would otherwise display "Token" in the preview card.
    _LST_ADDRESS_TO_LABEL = {
        "0xb0b84d294e0c75a6abe60171b70edeb2efd14a1b": ("slisBNB", "Lista DAO liquid staking"),
        "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": ("stETH", "Lido liquid staking"),
        "0xfa68fb4628dff1028cfec22b4162fccd0d45efb6": ("MATICX", "Stader liquid staking"),
        "0x2b2c81e08f1af8835a78bb2a90ae924ace0ea4be": ("sAVAX", "Benqi liquid staking"),
        "j1toso1uck3rlmjorhttrvwy9hj7x8v9yyac6y7kgcpn": ("jitoSOL", "Jito liquid staking"),
    }
    out_addr_norm = str(token_out).lower() if isinstance(token_out, str) else ""
    lst_meta = _LST_ADDRESS_TO_LABEL.get(out_addr_norm)
    if lst_meta:
        parsed["to_token_symbol"] = lst_meta[0]
        parsed["out_symbol"] = lst_meta[0]
        parsed["route_summary"] = lst_meta[1]
        parsed.setdefault("action_label", "stake")

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
    # Refuse to render zero/negative quote cards. Aggregator can occasionally
    # return a successful response with a 0 outAmount for ultra-illiquid pairs
    # — surface a real error instead of a card showing "0 → 0".
    try:
        in_num = float(amount_in_display or 0)
        out_num = float(dst_amount_display or 0)
    except (TypeError, ValueError):
        in_num, out_num = 0.0, 0.0
    if in_num <= 0 or out_num <= 0:
        return err_envelope(
            code="zero_quote",
            message=(
                "The aggregator returned a non-positive output amount, so we can't "
                "show a swap card. The pair may be illiquid or the input too small. "
                "Try a larger amount or a more liquid pair."
            ),
        )
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
