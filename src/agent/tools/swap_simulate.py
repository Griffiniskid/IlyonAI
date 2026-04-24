from src.agent.tools._base import ok_envelope, err_envelope
import json


async def simulate_swap(ctx, *, token_in, token_out, amount, chain="ethereum"):
    """Get swap quote using Jupiter for Solana or provide estimate for EVM."""
    
    # For Solana, use Jupiter
    if chain.lower() in ["solana", "sol"]:
        if hasattr(ctx.services, "jupiter") and ctx.services.jupiter:
            try:
                # Need token mint addresses - for now return placeholder
                # In production, you'd map symbols to mint addresses
                return ok_envelope(
                    data={
                        "token_in": token_in,
                        "token_out": token_out,
                        "amount": amount,
                        "chain": chain,
                        "note": "Solana swap quotes require token mint addresses. Please provide the token contract addresses.",
                    },
                    card_type="swap_quote",
                    card_payload={
                        "pay": {"token": token_in, "amount": amount},
                        "receive": {"token": token_out, "amount": "0"},
                        "rate": "N/A",
                        "router": "Jupiter",
                        "price_impact_pct": 0,
                    }
                )
            except Exception as e:
                print(f"Jupiter swap error: {e}")
    
    # For EVM chains, provide an estimate using price data
    if hasattr(ctx.services, "dexscreener") and ctx.services.dexscreener:
        try:
            # Search for token pair
            query = f"{token_in} {token_out}"
            pairs = await ctx.services.dexscreener.search_tokens(query, limit=5)
            
            if pairs:
                pair = pairs[0]
                price = float(pair.get("priceUsd", 0) or 0)
                
                # Rough estimate
                amount_in = float(amount)
                estimated_out = amount_in * price
                
                return ok_envelope(
                    data={
                        "token_in": token_in,
                        "token_out": token_out,
                        "amount_in": amount,
                        "estimated_out": f"{estimated_out:.6f}",
                        "chain": chain,
                        "price_usd": price,
                        "source": "DexScreener",
                        "note": "This is an estimate based on DEX prices. Actual swap may vary due to slippage and liquidity.",
                    },
                    card_type="swap_quote",
                    card_payload={
                        "pay": {"token": token_in, "amount": amount},
                        "receive": {"token": token_out, "amount": str(estimated_out)},
                        "rate": f"1 {token_in} ≈ {price:.6f} {token_out}",
                        "router": "Multi-DEX (via DexScreener)",
                        "price_impact_pct": 0.5,
                    }
                )
        except Exception as e:
            print(f"DexScreener swap error: {e}")
    
    return ok_envelope(
        data={
            "token_in": token_in,
            "token_out": token_out,
            "amount": amount,
            "chain": chain,
            "note": "Swap simulation requires token addresses for precise quotes. Connect your wallet to get accurate swap estimates.",
        },
        card_type="swap_quote",
        card_payload={
            "pay": {"token": token_in, "amount": amount},
            "receive": {"token": token_out, "amount": "0"},
            "rate": "N/A",
            "router": "Unknown",
            "price_impact_pct": 0,
        }
    )
