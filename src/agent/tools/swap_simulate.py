"""simulate_swap — price-based quote with real price lookups for major tokens."""
from __future__ import annotations

from src.agent.tools._base import ok_envelope


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
    try:
        amt = float(str(amount).replace(",", ""))
    except (TypeError, ValueError):
        amt = 0.0

    p_in = await _get_usd_price(ctx, token_in)
    p_out = await _get_usd_price(ctx, token_out)

    chain_l = (chain or "ethereum").lower()
    router = "Jupiter" if chain_l in ("solana", "sol") else "Multi-DEX (via DexScreener)"

    if p_in is None or p_out is None or p_out == 0:
        # Still emit a card, just without a firm estimate.
        return ok_envelope(
            data={
                "token_in": token_in,
                "token_out": token_out,
                "amount": str(amount),
                "chain": chain_l,
                "note": (
                    "We couldn't find USD prices for one or both legs — "
                    "try using the canonical symbol (e.g. USDC, WETH, SOL)."
                ),
            },
            card_type="swap_quote",
            card_payload={
                "pay": {"token": token_in, "amount": str(amount), "symbol": token_in},
                "receive": {"token": token_out, "amount": "0", "symbol": token_out},
                "rate": "N/A",
                "router": router,
                "price_impact_pct": 0.0,
            },
        )

    usd_in = amt * p_in
    estimated_out = usd_in / p_out
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
