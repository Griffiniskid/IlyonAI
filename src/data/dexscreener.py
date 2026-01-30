"""
DexScreener API client for fetching Solana DEX trading data.

This module provides an async client for interacting with the DexScreener API
to fetch Solana token pair information, liquidity data, and trading metrics.

NOTE: This client is exclusively for Solana blockchain analysis.
Only Solana pairs are supported - other chains are filtered out.
"""

import logging
import asyncio
from typing import Optional, Dict, List, Any
import aiohttp

logger = logging.getLogger(__name__)


class DexScreenerClient:
    """
    Async client for DexScreener API.

    Supports context manager for proper resource cleanup.

    Usage:
        # With context manager (recommended)
        async with DexScreenerClient() as client:
            data = await client.get_token("token_address")

        # Manual lifecycle
        client = DexScreenerClient()
        data = await client.get_token("token_address")
        await client.close()
    """

    BASE_URL = "https://api.dexscreener.com"
    DEFAULT_TIMEOUT = 15  # seconds
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES
    ):
        """
        Initialize DexScreener client.

        Args:
            session: Optional existing aiohttp session. If None, creates its own.
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts on failure
        """
        self._session = session
        self._owns_session = session is None
        self.timeout = timeout
        self.max_retries = max_retries

    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources"""
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """
        Ensure we have a valid session.

        Returns:
            Active aiohttp ClientSession
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
            self._owns_session = True
        return self._session

    async def close(self):
        """Close the aiohttp session if we own it"""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _make_request(
        self,
        url: str,
        retry_count: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with retry logic.

        Args:
            url: Full URL to request
            retry_count: Current retry attempt number

        Returns:
            JSON response dict or None on failure
        """
        try:
            session = await self._ensure_session()

            async with session.get(url) as resp:
                # Check status code
                if resp.status == 429:
                    # Rate limited
                    logger.warning(f"DexScreener rate limit hit for {url}")
                    if retry_count < self.max_retries:
                        await asyncio.sleep(self.RETRY_DELAY * (retry_count + 1))
                        return await self._make_request(url, retry_count + 1)
                    return None

                if resp.status != 200:
                    logger.warning(f"DexScreener API returned status {resp.status} for {url}")
                    return None

                # Parse JSON
                try:
                    data = await resp.json()
                    return data
                except Exception as e:
                    logger.error(f"Failed to parse DexScreener JSON: {e}")
                    return None

        except asyncio.TimeoutError:
            logger.warning(f"DexScreener request timeout for {url}")
            if retry_count < self.max_retries:
                await asyncio.sleep(self.RETRY_DELAY)
                return await self._make_request(url, retry_count + 1)
            return None

        except aiohttp.ClientError as e:
            logger.error(f"DexScreener client error: {e}")
            if retry_count < self.max_retries:
                await asyncio.sleep(self.RETRY_DELAY)
                return await self._make_request(url, retry_count + 1)
            return None

        except Exception as e:
            logger.error(f"Unexpected DexScreener error: {e}", exc_info=True)
            return None

    async def get_token(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get token information and trading pairs from DexScreener.

        Fetches all pairs for the token, filters for Solana pairs,
        and sorts by liquidity (highest first).

        Args:
            address: Solana token address

        Returns:
            Dict with structure:
            {
                'pairs': List[Dict],  # All pairs sorted by liquidity
                'main': Dict          # Highest liquidity pair
            }
            Returns None if token not found or on error.
        """
        url = f"{self.BASE_URL}/latest/dex/tokens/{address}"

        logger.info(f"🔍 Fetching DexScreener data for {address[:8]}...")

        data = await self._make_request(url)

        if not data:
            logger.warning(f"No DexScreener data for token {address[:8]}")
            return None

        # Validate response structure
        if 'pairs' not in data or not data['pairs']:
            logger.warning(f"DexScreener returned no pairs for {address[:8]}")
            return None

        # Filter for Solana pairs only (this bot is Solana-exclusive)
        pairs = [p for p in data['pairs'] if p.get('chainId') == 'solana']

        # No fallback to other chains - Solana only
        if not pairs:
            logger.warning(f"No Solana pairs found for {address[:8]} (non-Solana pairs ignored)")
            return None

        # Sort by liquidity (highest first)
        pairs.sort(
            key=lambda x: x.get('liquidity', {}).get('usd', 0) or 0,
            reverse=True
        )

        if not pairs:
            logger.warning(f"No valid pairs after filtering for {address[:8]}")
            return None

        result = {
            'pairs': pairs,
            'main': pairs[0]  # Highest liquidity pair
        }

        logger.info(
            f"✅ Found {len(pairs)} pairs for {address[:8]}, "
            f"main pair liquidity: ${result['main'].get('liquidity', {}).get('usd', 0):,.0f}"
        )

        return result

    async def get_pairs(self, address: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get all trading pairs for a token.

        Convenience method that returns just the pairs list.

        Args:
            address: Solana token address

        Returns:
            List of pair dicts sorted by liquidity, or None on error
        """
        result = await self.get_token(address)
        return result['pairs'] if result else None

    async def get_trending_tokens(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get trending Solana tokens by 24h volume.

        Uses DexScreener's token profiles endpoint to find popular Solana tokens.
        Returns full pair data format for compatibility with API routes.

        Args:
            limit: Max tokens to return

        Returns:
            List of Solana pair dicts in DexScreener format
        """
        logger.info(f"🔥 Fetching trending Solana tokens...")

        # Try the token profiles/latest endpoint first
        url = f"{self.BASE_URL}/token-profiles/latest/v1"
        data = await self._make_request(url)

        pairs = []

        if data and isinstance(data, list):
            # Get token addresses from profiles
            solana_tokens = [
                item.get("tokenAddress")
                for item in data
                if item.get("chainId") == "solana" and item.get("tokenAddress")
            ][:limit]

            # Fetch full pair data for each token
            for address in solana_tokens:
                token_data = await self.get_token(address)
                if token_data and token_data.get('main'):
                    pairs.append(token_data['main'])

        # Fallback: Try latest pairs endpoint
        if not pairs:
            url = f"{self.BASE_URL}/latest/dex/pairs/solana"
            data = await self._make_request(url)

            if data and "pairs" in data:
                all_pairs = data.get("pairs", [])
                # Sort by volume
                all_pairs.sort(
                    key=lambda x: float(x.get("volume", {}).get("h24", 0) or 0),
                    reverse=True
                )
                pairs = all_pairs[:limit]

        if not pairs:
            logger.warning("No trending tokens found")
            return []

        logger.info(f"✅ Found {len(pairs)} trending tokens")
        return pairs

    async def get_top_gainers(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get top gaining Solana tokens by price change.

        Args:
            limit: Max tokens to return

        Returns:
            List of Solana pair dicts sorted by 24h price change (highest first)
        """
        logger.info(f"📈 Fetching top gainers...")

        url = f"{self.BASE_URL}/latest/dex/pairs/solana"
        data = await self._make_request(url)

        if not data or "pairs" not in data:
            logger.warning("Could not fetch top gainers")
            return []

        pairs = data.get("pairs", [])

        # Filter out pairs with no price change data and sort by 24h gain
        valid_pairs = [
            p for p in pairs
            if p.get("priceChange", {}).get("h24") is not None
        ]
        valid_pairs.sort(
            key=lambda x: float(x.get("priceChange", {}).get("h24", 0) or 0),
            reverse=True
        )

        logger.info(f"✅ Found {len(valid_pairs[:limit])} top gainers")
        return valid_pairs[:limit]

    async def get_top_losers(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get top losing Solana tokens by price change.

        Args:
            limit: Max tokens to return

        Returns:
            List of Solana pair dicts sorted by 24h price change (lowest first)
        """
        logger.info(f"📉 Fetching top losers...")

        url = f"{self.BASE_URL}/latest/dex/pairs/solana"
        data = await self._make_request(url)

        if not data or "pairs" not in data:
            logger.warning("Could not fetch top losers")
            return []

        pairs = data.get("pairs", [])

        # Filter out pairs with no price change data and sort by 24h loss
        valid_pairs = [
            p for p in pairs
            if p.get("priceChange", {}).get("h24") is not None
        ]
        valid_pairs.sort(
            key=lambda x: float(x.get("priceChange", {}).get("h24", 0) or 0),
            reverse=False
        )

        logger.info(f"✅ Found {len(valid_pairs[:limit])} top losers")
        return valid_pairs[:limit]

    async def get_new_tokens(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get newly created Solana token pairs.

        Args:
            limit: Max tokens to return

        Returns:
            List of Solana pair dicts sorted by creation time (newest first)
        """
        logger.info(f"✨ Fetching new tokens...")

        url = f"{self.BASE_URL}/latest/dex/pairs/solana"
        data = await self._make_request(url)

        if not data or "pairs" not in data:
            logger.warning("Could not fetch new tokens")
            return []

        pairs = data.get("pairs", [])

        # Sort by pair creation time (newest first)
        valid_pairs = [p for p in pairs if p.get("pairCreatedAt")]
        valid_pairs.sort(
            key=lambda x: x.get("pairCreatedAt", 0),
            reverse=True
        )

        logger.info(f"✅ Found {len(valid_pairs[:limit])} new tokens")
        return valid_pairs[:limit]

    async def search_tokens(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for tokens by name or symbol.

        Args:
            query: Search query
            limit: Max results to return

        Returns:
            List of matching token dicts
        """
        logger.info(f"🔎 Searching for tokens: {query}")

        url = f"{self.BASE_URL}/latest/dex/search?q={query}"
        data = await self._make_request(url)

        if not data or "pairs" not in data:
            return []

        # Filter for Solana pairs
        pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "solana"]

        results = []
        seen_addresses = set()

        for pair in pairs[:limit * 2]:
            base = pair.get("baseToken", {})
            address = base.get("address", "")

            if address and address not in seen_addresses:
                seen_addresses.add(address)
                results.append({
                    "address": address,
                    "symbol": base.get("symbol", "???"),
                    "name": base.get("name", "Unknown"),
                    "priceUsd": pair.get("priceUsd"),
                    "liquidity": pair.get("liquidity", {}).get("usd", 0),
                })

        return results[:limit]
