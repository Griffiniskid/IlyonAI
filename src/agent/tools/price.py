from src.agent.tools._base import ok_envelope, err_envelope


async def _binance_price(symbol: str) -> float | None:
    """Fast, keyless USD price from Binance ({symbol}USDT). Used as a fallback
    when CoinGecko is down so a single feed outage doesn't fail price lookups."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": f"{symbol}USDT"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                if r.status == 200:
                    p = float((await r.json()).get("price") or 0)
                    return p if p > 0 else None
    except Exception:
        return None
    return None


async def get_token_price(ctx, *, token, chain="ethereum"):
    """Get current price for a token using real data sources."""
    import logging
    logger = logging.getLogger(__name__)

    symbol = token.upper()
    logger.warning(f"PRICE TOOL: Looking up {symbol} on {chain}")

    # Stablecoins are ~$1 — answer instantly, no feed dependency.
    if symbol in {"USDC", "USDT", "DAI", "BUSD", "FDUSD", "USDS", "PYUSD"}:
        data = {"symbol": symbol, "address": "", "chain": chain, "price_usd": "1.00",
                "change_24h_pct": 0, "market_cap": 0, "dex": "stablecoin"}
        return ok_envelope(data=data, card_type="token", card_payload=data)
    
    # For major tokens, try CoinGecko first for accurate prices
    major_tokens = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
                    "USDC": "usd-coin", "USDT": "tether", "BNB": "binancecoin",
                    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin",
                    "TRON": "tron", "LINK": "chainlink", "MATIC": "matic-network",
                    "WETH": "weth", "WBTC": "wrapped-bitcoin",
                    "AVAX": "avalanche-2", "ATOM": "cosmos", "DOT": "polkadot",
                    "JUP": "jupiter-exchange-solana", "PYTH": "pyth-network",
                    "RAY": "raydium", "ORCA": "orca", "JITO": "jito-governance-token",
                    "JITOSOL": "jito-staked-sol", "STETH": "staked-ether",
                    "RETH": "rocket-pool-eth"}
    
    # Native chain hints for major tokens (so the label says "Solana" for SOL).
    native_chain = {
        "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
        "BNB": "bsc", "USDC": "ethereum", "USDT": "ethereum",
        "TRON": "tron", "MATIC": "polygon", "XRP": "ripple",
        "ADA": "cardano", "DOGE": "dogecoin", "LINK": "ethereum",
    }

    if symbol in major_tokens:
        if hasattr(ctx.services, "price") and ctx.services.price:
            try:
                logger.warning(f"PRICE TOOL: Getting {symbol} price from CoinGecko")
                coin_id = major_tokens[symbol]
                price_data = await ctx.services.price.get_token_price([coin_id], vs_currencies="usd")
                logger.warning(f"PRICE TOOL: CoinGecko price data: {price_data}")

                if price_data and coin_id in price_data:
                    coin_data = price_data[coin_id]
                    usd = coin_data.get("usd")
                    if usd and float(usd) > 0:
                        data = {
                            "symbol": symbol,
                            "address": "",
                            "chain": native_chain.get(symbol, chain),
                            "price_usd": str(usd),
                            "change_24h_pct": coin_data.get("usd_24h_change", 0) or 0,
                            "market_cap": coin_data.get("usd_market_cap", 0) or 0,
                            "dex": "CoinGecko",
                        }
                        return ok_envelope(data=data, card_type="token", card_payload=data)
            except Exception as e:
                logger.warning(f"CoinGecko price error for {symbol}: {e}")

        # CoinGecko down → Binance fallback (fast, keyless). Only fail if BOTH
        # feeds are unavailable, so a single-source hiccup doesn't break the
        # most common question.
        _bp = await _binance_price(symbol)
        if _bp:
            data = {
                "symbol": symbol, "address": "", "chain": native_chain.get(symbol, chain),
                "price_usd": str(_bp), "change_24h_pct": 0, "market_cap": 0, "dex": "Binance",
            }
            return ok_envelope(data=data, card_type="token", card_payload=data)

        # Major tokens MUST NOT fall through to DexScreener search — those
        # queries return scam clones (e.g. "BTC" at $0.04 on some random DEX).
        # Return a clean err envelope instead.
        return err_envelope(
            "price_unavailable",
            f"Price feeds are temporarily unavailable for {symbol}. Please try again in a minute.",
            card_type="token",
        )
    
    # Non-major symbol: try Binance first (covers most CEX-listed tokens like
    # CAKE that aren't in the curated map and live on a non-default chain).
    if not (symbol.startswith("0X") or len(symbol) > 6):
        _bp = await _binance_price(symbol)
        if _bp:
            data = {"symbol": symbol, "address": "", "chain": chain,
                    "price_usd": str(_bp), "change_24h_pct": 0, "market_cap": 0, "dex": "Binance"}
            return ok_envelope(data=data, card_type="token", card_payload=data)

    # DexScreener symbol search returns SCAM CLONES for arbitrary tickers
    # (e.g. a fake "CAKE" at $0.0001). Only trust DexScreener when the input is
    # an ADDRESS (a contract address / Solana mint the user pasted) — that's an
    # exact lookup, not a fuzzy ticker match.
    _is_address = bool(
        (symbol.startswith("0X") and len(symbol) == 42)
        or (not symbol.startswith("0X") and 32 <= len(token.strip()) <= 44)
    )
    if _is_address and hasattr(ctx.services, "dexscreener") and ctx.services.dexscreener:
        try:
            logger.warning(f"PRICE TOOL: Calling DexScreener.search_tokens({token})")
            results = await ctx.services.dexscreener.search_tokens(token.strip(), limit=10, chain=chain)
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
    # Don't dead-end — ask for the contract address so we can resolve it by
    # address (works for long-tail / new tokens the symbol search misses).
    return err_envelope(
        "price_unavailable",
        f"No price found for \"{symbol}\" by its ticker. Paste the token's "
        f"contract address (its address on its chain, or its Solana mint "
        f"address) to get the exact price.",
        card_type="token",
    )
