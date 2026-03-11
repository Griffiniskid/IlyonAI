"""
CoinGecko API client for token metadata and market data.

Provides token information, pricing, and market data as a fallback/supplement
to DexScreener. Useful for tokens not yet listed on DEX aggregators.

API docs: https://docs.coingecko.com/reference/introduction
Free tier: 30 calls/min, no API key required.
Pro tier: Higher limits with API key.
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_PRO_URL = "https://pro-api.coingecko.com/api/v3"

# CoinGecko platform IDs for our supported chains
COINGECKO_PLATFORMS = {
    "ethereum": "ethereum",
    "bsc": "binance-smart-chain",
    "polygon": "polygon-pos",
    "arbitrum": "arbitrum-one",
    "optimism": "optimistic-ethereum",
    "avalanche": "avalanche",
    "base": "base",
    "solana": "solana",
}


class CoinGeckoClient:
    """
    Client for the CoinGecko API.

    Provides token metadata, market data, and pricing
    across all supported chains.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_key = api_key
        self._base_url = COINGECKO_PRO_URL if api_key else COINGECKO_BASE_URL

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Accept": "application/json"}
            if self._api_key:
                headers["x-cg-pro-api-key"] = self._api_key
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            )
        return self._session

    async def _get(self, endpoint: str, params: Dict[str, str] = None) -> Optional[Any]:
        """Make a GET request to the CoinGecko API."""
        session = await self._get_session()
        url = f"{self._base_url}/{endpoint}"
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    logger.warning("CoinGecko rate limit hit")
                    return None
                else:
                    logger.warning(f"CoinGecko API HTTP {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"CoinGecko API request failed: {e}")
            return None

    async def get_token_by_contract(
        self,
        contract_address: str,
        chain: str = "ethereum"
    ) -> Optional[Dict[str, Any]]:
        """
        Get token data by contract address.

        Args:
            contract_address: Token contract address.
            chain: Chain name (as ChainType.value).

        Returns:
            Token data dict or None.
        """
        platform = COINGECKO_PLATFORMS.get(chain, chain)
        data = await self._get(
            f"coins/{platform}/contract/{contract_address.lower()}"
        )
        if not data:
            return None

        return self._normalize_token(data)

    async def search_tokens(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for tokens/coins by name or symbol.

        Returns list of matching tokens with basic info.
        """
        data = await self._get("search", params={"query": query})
        if not data:
            return []

        coins = data.get("coins", [])
        results = []
        for coin in coins[:20]:
            results.append({
                "id": coin.get("id", ""),
                "name": coin.get("name", ""),
                "symbol": coin.get("symbol", ""),
                "market_cap_rank": coin.get("market_cap_rank"),
                "thumb": coin.get("thumb", ""),
                "large": coin.get("large", ""),
                "platforms": coin.get("platforms", {}),
            })

        return results

    async def get_token_price(
        self,
        token_ids: List[str],
        vs_currencies: str = "usd"
    ) -> Dict[str, Dict[str, float]]:
        """
        Get current prices for multiple tokens by CoinGecko ID.

        Args:
            token_ids: List of CoinGecko token IDs.
            vs_currencies: Comma-separated target currencies.

        Returns:
            Dict mapping token_id -> {currency: price}.
        """
        ids = ",".join(token_ids)
        data = await self._get(
            "simple/price",
            params={
                "ids": ids,
                "vs_currencies": vs_currencies,
                "include_24hr_change": "true",
                "include_market_cap": "true",
            }
        )
        return data or {}

    async def get_trending(self) -> List[Dict[str, Any]]:
        """Get trending tokens on CoinGecko."""
        data = await self._get("search/trending")
        if not data:
            return []

        coins = data.get("coins", [])
        results = []
        for entry in coins:
            item = entry.get("item", {})
            results.append({
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "symbol": item.get("symbol", ""),
                "market_cap_rank": item.get("market_cap_rank"),
                "price_btc": item.get("price_btc", 0),
                "score": item.get("score", 0),
                "thumb": item.get("thumb", ""),
            })

        return results

    async def get_token_market_data(self, coin_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed market data for a specific token."""
        data = await self._get(
            f"coins/{coin_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "community_data": "true",
                "developer_data": "true",
                "sparkline": "false",
            }
        )
        if not data:
            return None

        return self._normalize_token(data)

    def _normalize_token(self, data: Dict) -> Dict[str, Any]:
        """Normalize CoinGecko token data into a clean format."""
        market = data.get("market_data", {})
        community = data.get("community_data", {})
        developer = data.get("developer_data", {})

        return {
            "id": data.get("id", ""),
            "name": data.get("name", ""),
            "symbol": data.get("symbol", ""),
            "description": data.get("description", {}).get("en", ""),
            "image": data.get("image", {}).get("large", ""),
            "market_cap_rank": data.get("market_cap_rank"),
            "categories": data.get("categories", []),

            # Market data
            "price_usd": market.get("current_price", {}).get("usd", 0),
            "market_cap": market.get("market_cap", {}).get("usd", 0),
            "fdv": market.get("fully_diluted_valuation", {}).get("usd", 0),
            "total_volume": market.get("total_volume", {}).get("usd", 0),
            "price_change_24h": market.get("price_change_percentage_24h", 0),
            "price_change_7d": market.get("price_change_percentage_7d", 0),
            "price_change_30d": market.get("price_change_percentage_30d", 0),
            "ath": market.get("ath", {}).get("usd", 0),
            "ath_change": market.get("ath_change_percentage", {}).get("usd", 0),
            "circulating_supply": market.get("circulating_supply", 0),
            "total_supply": market.get("total_supply", 0),
            "max_supply": market.get("max_supply"),

            # Social/community
            "twitter_followers": community.get("twitter_followers", 0),
            "telegram_members": community.get("telegram_channel_user_count", 0),
            "reddit_subscribers": community.get("reddit_subscribers", 0),

            # Developer
            "github_forks": developer.get("forks", 0),
            "github_stars": developer.get("stars", 0),
            "github_commits_30d": developer.get("commit_count_4_weeks", 0),

            # Links
            "homepage": data.get("links", {}).get("homepage", [""])[0],
            "blockchain_sites": data.get("links", {}).get("blockchain_site", []),
            "chat_url": data.get("links", {}).get("chat_url", []),
            "twitter_handle": data.get("links", {}).get("twitter_screen_name", ""),
            "telegram_channel": data.get("links", {}).get("telegram_channel_identifier", ""),
            "subreddit": data.get("links", {}).get("subreddit_url", ""),
            "github_repos": data.get("links", {}).get("repos_url", {}).get("github", []),

            # Contract addresses by platform
            "platforms": data.get("platforms", {}),

            # Sentiment
            "sentiment_up": data.get("sentiment_votes_up_percentage", 0),
            "sentiment_down": data.get("sentiment_votes_down_percentage", 0),
        }

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("CoinGeckoClient closed")
