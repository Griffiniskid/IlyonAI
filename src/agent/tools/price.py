from src.agent.tools._base import ok_envelope, err_envelope


async def get_token_price(ctx, *, token, chain="ethereum"):
    """Get current price for a token using real data sources."""
    import logging
    logger = logging.getLogger(__name__)
    
    symbol = token.upper()
    logger.warning(f"PRICE TOOL: Looking up {symbol} on {chain}")
    
    # For major tokens, try CoinGecko first for accurate prices
    major_tokens = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", 
                    "USDC": "usd-coin", "USDT": "tether", "BNB": "binancecoin",
                    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin",
                    "TRON": "tron", "LINK": "chainlink", "MATIC": "matic-network"}
    
    if symbol in major_tokens:
        if hasattr(ctx.services, "price") and ctx.services.price:
            try:
                logger.warning(f"PRICE TOOL: Getting {symbol} price from CoinGecko")
                coin_id = major_tokens[symbol]
                price_data = await ctx.services.price.get_token_price([coin_id], vs_currencies="usd")
                logger.warning(f"PRICE TOOL: CoinGecko price data: {price_data}")
                
                if price_data and coin_id in price_data:
                    coin_data = price_data[coin_id]
                    data = {
                        "symbol": symbol,
                        "address": "",
                        "chain": chain,
                        "price_usd": str(coin_data.get("usd", 0)),
                        "change_24h_pct": coin_data.get("usd_24h_change", 0) or 0,
                        "market_cap": coin_data.get("usd_market_cap", 0) or 0,
                    }
                    return ok_envelope(data=data, card_type="token", card_payload=data)
            except Exception as e:
                logger.warning(f"CoinGecko price error for {symbol}: {e}")
    
    # For other tokens, try DexScreener (real-time DEX data)
    if hasattr(ctx.services, "dexscreener") and ctx.services.dexscreener:
        try:
            logger.warning(f"PRICE TOOL: Calling DexScreener.search_tokens({symbol})")
            results = await ctx.services.dexscreener.search_tokens(symbol, limit=10, chain=chain)
            logger.warning(f"PRICE TOOL: DexScreener returned {len(results)} results")
            if results:
                # Sort by liquidity to find the main token (not random clones)
                results.sort(key=lambda x: float(x.get("liquidity", 0) or 0), reverse=True)
                best = results[0]
                logger.warning(f"PRICE TOOL: Best result: {best}")
                
                price = float(best.get("priceUsd", 0) or 0)
                liquidity = float(best.get("liquidity", 0) or 0)
                
                data = {
                    "symbol": best.get("symbol", symbol),
                    "address": best.get("address", ""),
                    "chain": best.get("chain", chain),
                    "price_usd": str(price),
                    "change_24h_pct": 0.0,
                    "liquidity": liquidity,
                    "dex": best.get("dex", "unknown"),
                    "name": best.get("name", symbol),
                }
                return ok_envelope(data=data, card_type="token", card_payload=data)
        except Exception as e:
            logger.warning(f"DexScreener price error: {e}")
    
    # Fallback to CoinGecko search for unknown tokens
    if hasattr(ctx.services, "price") and ctx.services.price:
        try:
            logger.warning(f"PRICE TOOL: Searching CoinGecko for {symbol}")
            search_results = await ctx.services.price.search_tokens(symbol)
            if search_results:
                coin_id = search_results[0].get("id", symbol.lower())
                price_data = await ctx.services.price.get_token_price([coin_id], vs_currencies="usd")
                if price_data and coin_id in price_data:
                    coin_data = price_data[coin_id]
                    data = {
                        "symbol": symbol,
                        "address": "",
                        "chain": chain,
                        "price_usd": str(coin_data.get("usd", 0)),
                        "change_24h_pct": coin_data.get("usd_24h_change", 0) or 0,
                        "market_cap": coin_data.get("usd_market_cap", 0) or 0,
                    }
                    return ok_envelope(data=data, card_type="token", card_payload=data)
        except Exception as e:
            logger.warning(f"CoinGecko fallback error: {e}")
    
    logger.warning(f"PRICE TOOL: All data sources failed for {symbol}")
    return err_envelope(
        "price_unavailable",
        f"Unable to fetch price for {symbol}. The token may not be traded on major DEXs yet.",
        card_type="token"
    )
