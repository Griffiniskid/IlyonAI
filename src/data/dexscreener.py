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

    async def _fetch_tokens_batch(
        self,
        addresses: List[str],
        existing_addresses: set
    ) -> List[Dict[str, Any]]:
        """
        Fetch multiple tokens in parallel batches.
        
        Args:
            addresses: List of token addresses to fetch
            existing_addresses: Set of already-fetched addresses to skip
            
        Returns:
            List of pair dicts for successfully fetched tokens
        """
        pairs = []
        # Filter out already-fetched addresses
        addresses_to_fetch = [a for a in addresses if a and a not in existing_addresses]
        
        if not addresses_to_fetch:
            return pairs
            
        # Fetch in batches of 5 to avoid rate limits
        batch_size = 5
        for i in range(0, len(addresses_to_fetch), batch_size):
            batch = addresses_to_fetch[i:i + batch_size]
            
            # Create tasks for parallel fetching
            tasks = [self.get_token(addr) for addr in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for addr, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.debug(f"Batch fetch error for {addr}: {result}")
                    continue
                if result and result.get('main'):
                    main_pair = result['main']
                    token_addr = main_pair.get('baseToken', {}).get('address')
                    if token_addr and token_addr not in existing_addresses:
                        pairs.append(main_pair)
                        existing_addresses.add(token_addr)
            
            # Small delay between batches to avoid rate limits
            if i + batch_size < len(addresses_to_fetch):
                await asyncio.sleep(0.3)
        
        return pairs

    async def _search_solana_pairs(
        self,
        keywords: List[str],
        limit_per_keyword: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Search for Solana pairs using multiple keywords.
        
        Uses the search API which returns full pair data directly,
        avoiding the need for individual token lookups.
        
        Args:
            keywords: List of search terms
            limit_per_keyword: Max results per keyword
            
        Returns:
            List of unique Solana pair dicts
        """
        pairs = []
        seen_addresses = set()
        
        for keyword in keywords:
            try:
                url = f"{self.BASE_URL}/latest/dex/search?q={keyword}"
                data = await self._make_request(url)
                
                if data and 'pairs' in data:
                    solana_pairs = [
                        p for p in data['pairs']
                        if p.get('chainId') == 'solana'
                    ][:limit_per_keyword]
                    
                    for pair in solana_pairs:
                        addr = pair.get('baseToken', {}).get('address')
                        if addr and addr not in seen_addresses:
                            # Ensure the pair has basic required fields
                            if pair.get('priceUsd') and pair.get('liquidity'):
                                pairs.append(pair)
                                seen_addresses.add(addr)
                
                # Small delay between searches
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.debug(f"Search for '{keyword}' failed: {e}")
                continue
        
        return pairs

    async def get_trending_tokens(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get trending Solana tokens by 24h volume.

        Uses multiple data sources:
        1. DexScreener's boosted tokens endpoint
        2. Token profiles (recently updated)
        3. Search API with popular Solana keywords as fallback

        Args:
            limit: Max tokens to return

        Returns:
            List of Solana pair dicts in DexScreener format
        """
        logger.info(f"🔥 Fetching trending Solana tokens...")

        pairs = []
        existing_addresses = set()

        # Try boosted tokens first (these are trending/promoted)
        try:
            url = f"{self.BASE_URL}/token-boosts/top/v1"
            data = await self._make_request(url)

            if data and isinstance(data, list):
                solana_tokens = [
                    item.get("tokenAddress")
                    for item in data
                    if item.get("chainId") == "solana" and item.get("tokenAddress")
                ][:25]

                # Parallel batch fetch
                new_pairs = await self._fetch_tokens_batch(solana_tokens, existing_addresses)
                pairs.extend(new_pairs)
                
        except Exception as e:
            logger.warning(f"Token boosts fetch failed: {e}")

        # Supplement with token profiles
        if len(pairs) < limit:
            try:
                url = f"{self.BASE_URL}/token-profiles/latest/v1"
                data = await self._make_request(url)

                if data and isinstance(data, list):
                    solana_profiles = [
                        item.get("tokenAddress")
                        for item in data
                        if item.get("chainId") == "solana" and item.get("tokenAddress")
                    ][:25]

                    new_pairs = await self._fetch_tokens_batch(solana_profiles, existing_addresses)
                    # Filter for minimum volume/liquidity
                    for pair in new_pairs:
                        vol = float(pair.get("volume", {}).get("h24", 0) or 0)
                        liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                        if vol > 500 and liq > 2000:
                            pairs.append(pair)
                            
            except Exception as e:
                logger.warning(f"Token profiles fetch failed: {e}")

        # Fallback: Use search API with popular keywords if still need more
        if len(pairs) < limit:
            logger.info("Using search fallback for trending tokens...")
            search_keywords = ["SOL", "BONK", "WIF", "PEPE", "meme", "pump", "ai", "cat", "dog"]
            
            search_pairs = await self._search_solana_pairs(search_keywords, limit_per_keyword=10)
            
            for pair in search_pairs:
                addr = pair.get('baseToken', {}).get('address')
                if addr and addr not in existing_addresses:
                    vol = float(pair.get("volume", {}).get("h24", 0) or 0)
                    liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                    if vol > 500 and liq > 2000:
                        pairs.append(pair)
                        existing_addresses.add(addr)
                if len(pairs) >= limit * 2:
                    break

        # Sort by volume (highest first)
        pairs.sort(
            key=lambda x: float(x.get("volume", {}).get("h24", 0) or 0),
            reverse=True
        )

        if not pairs:
            logger.warning("No trending tokens found")
            return []

        logger.info(f"✅ Found {len(pairs[:limit])} trending tokens")
        return pairs[:limit]

    async def get_top_gainers(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get top gaining Solana tokens by price change.

        Uses search API as primary source since it returns complete pair data directly,
        supplemented by boosted tokens endpoint.

        Args:
            limit: Max tokens to return

        Returns:
            List of Solana pair dicts sorted by 24h price change (highest first)
        """
        logger.info(f"📈 Fetching top gainers...")

        all_pairs = []
        existing_addresses = set()

        # Use search API with multiple keywords - returns full pair data directly
        # This is more reliable than fetching individual tokens
        search_keywords = [
            "SOL", "BONK", "WIF", "PEPE", "meme", "pump", "moon",
            "ai", "cat", "dog", "trump", "elon", "doge", "shib",
            "popcat", "brett", "jup", "ray", "orca"
        ]
        
        search_pairs = await self._search_solana_pairs(search_keywords, limit_per_keyword=25)
        logger.info(f"Search API returned {len(search_pairs)} pairs for gainers")
        
        for pair in search_pairs:
            addr = pair.get('baseToken', {}).get('address')
            if addr and addr not in existing_addresses:
                all_pairs.append(pair)
                existing_addresses.add(addr)

        # Supplement with boosted tokens if needed
        if len(all_pairs) < limit * 2:
            try:
                url = f"{self.BASE_URL}/token-boosts/top/v1"
                data = await self._make_request(url)

                if data and isinstance(data, list):
                    solana_tokens = [
                        item.get("tokenAddress")
                        for item in data
                        if item.get("chainId") == "solana" and item.get("tokenAddress")
                    ][:20]

                    new_pairs = await self._fetch_tokens_batch(solana_tokens, existing_addresses)
                    all_pairs.extend(new_pairs)
                    logger.info(f"Boosted tokens added {len(new_pairs)} pairs")
                    
            except Exception as e:
                logger.warning(f"Boosted tokens fetch failed: {e}")

        # Filter for gainers with minimum liquidity (lowered threshold)
        gainers = []
        for pair in all_pairs:
            price_change = float(pair.get("priceChange", {}).get("h24", 0) or 0)
            liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            volume = float(pair.get("volume", {}).get("h24", 0) or 0)
            # Include gainers with minimum liquidity and some volume
            if price_change > 0 and liquidity >= 500 and volume >= 100:
                gainers.append(pair)

        # Sort by price change (highest gains first)
        gainers.sort(
            key=lambda x: float(x.get("priceChange", {}).get("h24", 0) or 0),
            reverse=True
        )

        logger.info(f"✅ Found {len(gainers[:limit])} top gainers (filtered from {len(all_pairs)} pairs)")
        return gainers[:limit]

    async def get_top_losers(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get top losing Solana tokens by price change.

        Uses search API as primary source since it returns complete pair data directly,
        supplemented by boosted tokens endpoint.

        Args:
            limit: Max tokens to return

        Returns:
            List of Solana pair dicts sorted by 24h price change (lowest first)
        """
        logger.info(f"📉 Fetching top losers...")

        all_pairs = []
        existing_addresses = set()

        # Use search API with multiple keywords - returns full pair data directly
        search_keywords = [
            "SOL", "BONK", "WIF", "PEPE", "meme", "pump",
            "ai", "cat", "dog", "trump", "elon", "doge", "shib",
            "popcat", "brett", "jup", "ray", "orca", "pyth"
        ]
        
        search_pairs = await self._search_solana_pairs(search_keywords, limit_per_keyword=25)
        logger.info(f"Search API returned {len(search_pairs)} pairs for losers")
        
        for pair in search_pairs:
            addr = pair.get('baseToken', {}).get('address')
            if addr and addr not in existing_addresses:
                all_pairs.append(pair)
                existing_addresses.add(addr)

        # Supplement with boosted tokens if needed
        if len(all_pairs) < limit * 2:
            try:
                url = f"{self.BASE_URL}/token-boosts/top/v1"
                data = await self._make_request(url)

                if data and isinstance(data, list):
                    solana_tokens = [
                        item.get("tokenAddress")
                        for item in data
                        if item.get("chainId") == "solana" and item.get("tokenAddress")
                    ][:20]

                    new_pairs = await self._fetch_tokens_batch(solana_tokens, existing_addresses)
                    all_pairs.extend(new_pairs)
                    logger.info(f"Boosted tokens added {len(new_pairs)} pairs")
                    
            except Exception as e:
                logger.warning(f"Boosted tokens fetch failed: {e}")

        # Filter for losers with minimum liquidity (lowered threshold)
        losers = []
        for pair in all_pairs:
            price_change = float(pair.get("priceChange", {}).get("h24", 0) or 0)
            liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            volume = float(pair.get("volume", {}).get("h24", 0) or 0)
            # Include losers with minimum liquidity and some volume
            if price_change < 0 and liquidity >= 500 and volume >= 100:
                losers.append(pair)

        # Sort by price change (biggest losers first)
        losers.sort(
            key=lambda x: float(x.get("priceChange", {}).get("h24", 0) or 0),
            reverse=False
        )

        logger.info(f"✅ Found {len(losers[:limit])} top losers (filtered from {len(all_pairs)} pairs)")
        return losers[:limit]

    async def get_new_tokens(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get newly created Solana token pairs.

        Uses search API as primary source for broad coverage,
        supplemented by token profiles endpoint.

        Args:
            limit: Max tokens to return

        Returns:
            List of Solana pair dicts sorted by creation time (newest first)
        """
        logger.info(f"✨ Fetching new tokens...")

        all_pairs = []
        existing_addresses = set()

        # Use search API with keywords that often appear in new tokens
        search_keywords = [
            "pump", "new", "launch", "fair", "meme", "ai", "cat", "dog",
            "moon", "gem", "baby", "mini", "inu", "coin", "token", "sol"
        ]
        
        search_pairs = await self._search_solana_pairs(search_keywords, limit_per_keyword=20)
        logger.info(f"Search API returned {len(search_pairs)} pairs for new tokens")
        
        for pair in search_pairs:
            addr = pair.get('baseToken', {}).get('address')
            if addr and addr not in existing_addresses:
                all_pairs.append(pair)
                existing_addresses.add(addr)

        # Supplement with token profiles (ordered by recent activity/creation)
        if len(all_pairs) < limit * 3:
            try:
                url = f"{self.BASE_URL}/token-profiles/latest/v1"
                data = await self._make_request(url)

                if data and isinstance(data, list):
                    solana_profiles = [
                        item.get("tokenAddress")
                        for item in data
                        if item.get("chainId") == "solana" and item.get("tokenAddress")
                    ][:30]

                    new_pairs = await self._fetch_tokens_batch(solana_profiles, existing_addresses)
                    all_pairs.extend(new_pairs)
                    logger.info(f"Token profiles added {len(new_pairs)} pairs")
                    
            except Exception as e:
                logger.warning(f"Token profiles fetch failed: {e}")

        # Filter for tokens with minimum liquidity (lowered threshold for new tokens)
        new_tokens = []
        for pair in all_pairs:
            liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            volume = float(pair.get("volume", {}).get("h24", 0) or 0)
            created_at = pair.get("pairCreatedAt", 0)
            # Include if has minimum liquidity
            if liquidity >= 200 and (volume >= 50 or created_at):
                new_tokens.append(pair)

        # Sort by creation time (newest first), fallback to 0 for unknown
        new_tokens.sort(
            key=lambda x: x.get("pairCreatedAt", 0) or 0,
            reverse=True
        )

        logger.info(f"✅ Found {len(new_tokens[:limit])} new tokens")
        return new_tokens[:limit]

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
