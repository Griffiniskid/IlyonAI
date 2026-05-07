"""simulate_swap — price-based quote with real price lookups for major tokens."""
from __future__ import annotations

from src.agent.intent.validation import (
    is_stop_word,
    is_valid_symbol_shape,
    validate_quote_output,
    validate_swap_params,
)
from src.agent.tools._base import err_envelope, ok_envelope


# Chain alias → numeric id for validation. Mirrors simple_runtime CHAIN_IDS but
# kept local so swap_simulate doesn't depend on runtime internals.
_CHAIN_ID_BY_NAME = {
    "ethereum": 1, "eth": 1, "mainnet": 1,
    "arbitrum": 42161, "arb": 42161,
    "base": 8453,
    "optimism": 10, "op": 10,
    "polygon": 137, "matic": 137,
    "bsc": 56, "bnb": 56,
    "avalanche": 43114, "avax": 43114,
    "solana": 101, "sol": 101,
}


_MAJOR_CG_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "USDC": "usd-coin", "USDT": "tether", "DAI": "dai",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
    "DOGE": "dogecoin", "TRON": "tron", "LINK": "chainlink",
    "MATIC": "matic-network", "AVAX": "avalanche-2", "ATOM": "cosmos",
    "WETH": "weth", "WBTC": "wrapped-bitcoin", "JUP": "jupiter-exchange-solana",
    "PYTH": "pyth-network", "RAY": "raydium", "ORCA": "orca",
    "JITO": "jito-governance-token", "JITOSOL": "jito-staked-sol",
    "STETH": "staked-ether", "RETH": "rocket-pool-eth",
}


async def _get_usd_price(ctx, symbol: str) -> float | None:
    sym = symbol.upper()
    cg_id = _MAJOR_CG_IDS.get(sym)
    price_client = getattr(ctx.services, "price", None)
    if cg_id and price_client is not None:
        try:
            data = await price_client.get_token_price([cg_id], vs_currencies="usd")
            if data and cg_id in data:
                p = data[cg_id].get("usd")
                if p:
                    return float(p)
        except Exception:
            pass
    # Fallback to DexScreener for less-known tokens
    dex = getattr(ctx.services, "dexscreener", None)
    if dex is not None:
        try:
            results = await dex.search_tokens(sym, limit=5)
            if results:
                results.sort(key=lambda x: float(x.get("liquidity", 0) or 0), reverse=True)
                p = float(results[0].get("priceUsd", 0) or 0)
                if p > 0:
                    return p
        except Exception:
            pass
    return None


async def simulate_swap(ctx, *, token_in, token_out, amount, chain="ethereum"):
    """Quote a swap using independent USD prices for both legs.

    This does not require token contract addresses — it composes the quote
    from live USD prices (CoinGecko for majors, DexScreener fallback) so
    "10 SOL to USDC" always returns a numerically meaningful estimate.
    """
    # Reject obviously-bad token captures up front. The LLM tool-call path can
    # otherwise hand us "WALLET" or "FROM" as a symbol.
    if (not is_valid_symbol_shape(token_in)) or is_stop_word(token_in):
        return err_envelope(
            code="invalid_token",
            message=(
                f"'{token_in}' isn't a valid token symbol. "
                f"Try the canonical ticker — for example: SOL, USDC, ETH."
            ),
        )
    if (not is_valid_symbol_shape(token_out)) or is_stop_word(token_out):
        return err_envelope(
            code="invalid_token",
            message=(
                f"'{token_out}' isn't a valid token symbol. "
                f"Try the canonical ticker — for example: WBNB, USDC, ETH."
            ),
        )

    try:
        amt = float(str(amount).replace(",", ""))
    except (TypeError, ValueError):
        amt = 0.0
    if amt <= 0:
        return err_envelope(
            code="invalid_amount",
            message="Amount must be a positive number. Try 'swap 0.1 SOL to USDC'.",
        )

    chain_l = (chain or "ethereum").lower()
    chain_id = _CHAIN_ID_BY_NAME.get(chain_l)
    # Cross-chain / wrong-chain guard against the same-named token mismatch
    # that lets "swap 0.1 SOL for WETH" silently route to Jupiter.
    pre = validate_swap_params(
        token_in=token_in.upper(),
        token_out=token_out.upper(),
        chain_id=chain_id,
        amount_in=str(int(amt * 10**6)),  # synthetic positive base-units
    )
    if not pre.ok and pre.error_code in {"cross_chain", "token_not_on_chain", "same_token"}:
        return err_envelope(
            code=pre.error_code,
            message=pre.user_message or "Swap rejected by validation.",
        )

    p_in = await _get_usd_price(ctx, token_in)
    p_out = await _get_usd_price(ctx, token_out)

    router = "Jupiter" if chain_l in ("solana", "sol") else "Multi-DEX (via DexScreener)"

    if p_in is None or p_out is None or p_out == 0:
        return err_envelope(
            code="quote_unavailable",
            message=(
                f"I couldn't find a live USD price for "
                f"{token_in if p_in is None else token_out}. "
                f"Use the canonical symbol (e.g. USDC, WETH, SOL) or try a different pair."
            ),
        )

    usd_in = amt * p_in
    estimated_out = usd_in / p_out
    # Refuse to emit a card if the quote rounds to zero — happens when amount
    # is tiny against an expensive output token, or when prices are stale.
    post = validate_quote_output(
        amount_in_human=amt,
        amount_out_human=estimated_out,
    )
    if not post.ok:
        return err_envelope(
            code=post.error_code or "zero_quote",
            message=post.user_message or "Quote produced a non-positive output.",
        )
    # Simple price-impact heuristic: bigger trades on illiquid routes assume more impact.
    est_impact = 0.10 if usd_in < 10_000 else (0.30 if usd_in < 100_000 else 0.60)

    rate_str = f"1 {token_in} ≈ {p_in / p_out:.6f} {token_out}"
    return ok_envelope(
        data={
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": str(amount),
            "estimated_out": f"{estimated_out:,.6f}",
            "chain": chain_l,
            "price_in_usd": p_in,
            "price_out_usd": p_out,
            "rate": rate_str,
            "router": router,
            "price_impact_pct": est_impact,
            "source": "CoinGecko+DexScreener blend",
        },
        card_type="swap_quote",
        card_payload={
            "pay": {"token": token_in, "amount": str(amount), "symbol": token_in},
            "receive": {
                "token": token_out,
                "amount": f"{estimated_out:,.6f}",
                "symbol": token_out,
            },
            "rate": rate_str,
            "router": router,
            "price_impact_pct": est_impact,
        },
    )
