"""
DexScreener API client for fetching multi-chain DEX trading data.

This module provides an async client for interacting with the DexScreener API
to fetch token pair information, liquidity data, and trading metrics across
Solana and the major EVM chains supported by Ilyon AI.
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

    CHAIN_ALIASES = {
        "eth": "ethereum",
        "bsc": "bsc",
        "bnb": "bsc",
        "bnb chain": "bsc",
        "binance smart chain": "bsc",
        "matic": "polygon",
        "poly": "polygon",
        "arb": "arbitrum",
        "arbitrum one": "arbitrum",
        "op": "optimism",
        "avax": "avalanche",
        "sol": "solana",
    }

    SUPPORTED_TRENDING_CHAINS = {
        "solana",
        "ethereum",
        "base",
        "arbitrum",
        "bsc",
        "polygon",
        "optimism",
        "avalanche",
    }

    TRENDING_SEARCH_KEYWORDS = [
        "usdc",
        "eth",
        "sol",
        "btc",
        "ai",
        "defi",
        "meme",
        "doge",
        "pepe",
        "cat",
        "pump",
        "launch",
    ]

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
    ) -> Optional[Any]:
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

    def _normalize_chain(self, chain: Optional[str]) -> Optional[str]:
        if not chain:
            return None
        normalized = chain.strip().lower()
        return self.CHAIN_ALIASES.get(normalized, normalized)

    async def get_token(self, address: str, chain: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get token information and trading pairs from DexScreener.

        Fetches all pairs for the token, optionally filters for a specific chain,
        and sorts by liquidity (highest first).

        Args:
            address: Token address
            chain: Optional chain filter (solana, ethereum, base, arbitrum, bsc,
                polygon, optimism, avalanche). If omitted, the highest-liquidity
                pair across all chains is returned.

        Returns:
            Dict with structure:
            {
                'pairs': List[Dict],  # All pairs sorted by liquidity
                'main': Dict          # Highest liquidity pair
            }
            Returns None if token not found or on error.
        """
        url = f"{self.BASE_URL}/latest/dex/tokens/{address}"

        normalized_chain = self._normalize_chain(chain)
        logger.info(
            f"Fetching DexScreener data for {address[:8]}..."
            f" (chain={normalized_chain or 'all'})"
        )

        data = await self._make_request(url)

        if not data:
            logger.warning(f"No DexScreener data for token {address[:8]}")
            return None

        # Validate response structure
        if 'pairs' not in data or not data['pairs']:
            logger.warning(f"DexScreener returned no pairs for {address[:8]}")
            return None

        pairs = data['pairs']
        if normalized_chain:
            pairs = [p for p in pairs if self._normalize_chain(p.get('chainId')) == normalized_chain]

        if not pairs:
            logger.warning(
                f"No DexScreener pairs found for {address[:8]}"
                f" on chain={normalized_chain or 'all'}"
            )
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
            f"Found {len(pairs)} pairs for {address[:8]}, "
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
        candidates: List[Dict[str, str]],
        existing_ids: set,
    ) -> List[Dict[str, Any]]:
        """Fetch token pairs in batches while preserving chain context."""
        pairs: List[Dict[str, Any]] = []
        candidates_to_fetch = []
        for candidate in candidates:
            address = candidate.get("address", "")
            chain = self._normalize_chain(candidate.get("chain"))
            if not address or not chain:
                continue
            identity = f"{chain}:{address.lower()}"
            if identity in existing_ids:
                continue
            candidates_to_fetch.append({"address": address, "chain": chain})

        if not candidates_to_fetch:
            return pairs

        batch_size = 5
        for i in range(0, len(candidates_to_fetch), batch_size):
            batch = candidates_to_fetch[i:i + batch_size]
            tasks = [self.get_token(item["address"], chain=item["chain"]) for item in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for candidate, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.debug(f"Batch fetch error for {candidate}: {result}")
                    continue
                if not isinstance(result, dict):
                    continue
                if not result.get("main"):
                    continue

                main_pair = result["main"]
                token_addr = main_pair.get("baseToken", {}).get("address")
                pair_chain = self._normalize_chain(main_pair.get("chainId") or candidate.get("chain"))
                if not token_addr or not pair_chain:
                    continue

                identity = f"{pair_chain}:{token_addr.lower()}"
                if identity in existing_ids:
                    continue

                pairs.append(main_pair)
                existing_ids.add(identity)

            if i + batch_size < len(candidates_to_fetch):
                await asyncio.sleep(0.3)

        return pairs

    async def _search_market_pairs(
        self,
        keywords: List[str],
        chain: Optional[str] = None,
        limit_per_keyword: int = 12,
    ) -> List[Dict[str, Any]]:
        """Search DexScreener pairs across supported chains."""
        pairs: List[Dict[str, Any]] = []
        seen_ids = set()
        normalized_chain = self._normalize_chain(chain)

        for keyword in keywords:
            try:
                url = f"{self.BASE_URL}/latest/dex/search?q={keyword}"
                data = await self._make_request(url)
                if not data or "pairs" not in data:
                    continue

                filtered_pairs = []
                for pair in data["pairs"]:
                    pair_chain = self._normalize_chain(pair.get("chainId"))
                    if not pair_chain or pair_chain not in self.SUPPORTED_TRENDING_CHAINS:
                        continue
                    if normalized_chain and pair_chain != normalized_chain:
                        continue
                    filtered_pairs.append(pair)

                for pair in filtered_pairs[:limit_per_keyword]:
                    address = pair.get("baseToken", {}).get("address")
                    pair_chain = self._normalize_chain(pair.get("chainId"))
                    if not address or not pair_chain:
                        continue
                    identity = f"{pair_chain}:{address.lower()}"
                    if identity in seen_ids:
                        continue
                    if pair.get("priceUsd") and pair.get("liquidity"):
                        pairs.append(pair)
                        seen_ids.add(identity)

                await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug(f"Search for '{keyword}' failed: {e}")
                continue

        return pairs

    async def _collect_candidate_tokens(
        self,
        chain: Optional[str] = None,
        per_source_limit: int = 40,
    ) -> List[Dict[str, str]]:
        """Collect token candidates from boosted/profile endpoints."""
        normalized_chain = self._normalize_chain(chain)
        candidates: List[Dict[str, str]] = []
        seen_ids = set()

        for endpoint in ("/token-boosts/top/v1", "/token-profiles/latest/v1"):
            try:
                data = await self._make_request(f"{self.BASE_URL}{endpoint}")
                if not data or not isinstance(data, list):
                    continue

                for item in data:
                    if not isinstance(item, dict):
                        continue
                    item_chain = self._normalize_chain(item.get("chainId"))
                    address = item.get("tokenAddress")
                    if not item_chain or not address:
                        continue
                    if item_chain not in self.SUPPORTED_TRENDING_CHAINS:
                        continue
                    if normalized_chain and item_chain != normalized_chain:
                        continue

                    identity = f"{item_chain}:{address.lower()}"
                    if identity in seen_ids:
                        continue

                    seen_ids.add(identity)
                    candidates.append({"address": address, "chain": item_chain})
                    if len(candidates) >= per_source_limit * 2:
                        break
            except Exception as e:
                logger.warning(f"Candidate collection failed for {endpoint}: {e}")

        return candidates

    async def _collect_market_pairs(
        self,
        chain: Optional[str] = None,
        limit_hint: int = 20,
    ) -> List[Dict[str, Any]]:
        """Collect market pairs for trending/gainers/losers/new flows."""
        pairs: List[Dict[str, Any]] = []
        seen_ids = set()

        candidates = await self._collect_candidate_tokens(chain=chain, per_source_limit=max(30, limit_hint * 2))
        pairs.extend(await self._fetch_tokens_batch(candidates, seen_ids))

        if len(pairs) < limit_hint * 3:
            search_pairs = await self._search_market_pairs(
                self.TRENDING_SEARCH_KEYWORDS,
                chain=chain,
                limit_per_keyword=max(6, limit_hint // 2),
            )
            for pair in search_pairs:
                address = pair.get("baseToken", {}).get("address")
                pair_chain = self._normalize_chain(pair.get("chainId"))
                if not address or not pair_chain:
                    continue
                identity = f"{pair_chain}:{address.lower()}"
                if identity in seen_ids:
                    continue
                seen_ids.add(identity)
                pairs.append(pair)

        return pairs

    async def get_trending_tokens(
        self,
        limit: int = 20,
        chain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        logger.info(f"🔥 Fetching trending tokens (chain={chain or 'all'})...")
        pairs: List[Dict[str, Any]] = await self._collect_market_pairs(chain=chain, limit_hint=limit)
        pairs = [
            pair for pair in pairs
            if float(pair.get("volume", {}).get("h24", 0) or 0) >= 500
            and float(pair.get("liquidity", {}).get("usd", 0) or 0) >= 2000
        ]
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
        limit: int = 20,
        chain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        logger.info(f"📈 Fetching top gainers (chain={chain or 'all'})...")
        all_pairs: List[Dict[str, Any]] = await self._collect_market_pairs(chain=chain, limit_hint=limit)
        gainers = []
        for pair in all_pairs:
            price_change = float(pair.get("priceChange", {}).get("h24", 0) or 0)
            liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            volume = float(pair.get("volume", {}).get("h24", 0) or 0)
            if price_change > 0 and liquidity >= 100 and volume >= 50:
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
        limit: int = 20,
        chain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        logger.info(f"📉 Fetching top losers (chain={chain or 'all'})...")
        all_pairs: List[Dict[str, Any]] = await self._collect_market_pairs(chain=chain, limit_hint=limit)
        losers = []
        for pair in all_pairs:
            price_change = float(pair.get("priceChange", {}).get("h24", 0) or 0)
            liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            volume = float(pair.get("volume", {}).get("h24", 0) or 0)
            if price_change < 0 and liquidity >= 100 and volume >= 50:
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
        limit: int = 20,
        chain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        import time
        logger.info(f"✨ Fetching new tokens (chain={chain or 'all'})...")

        all_pairs: List[Dict[str, Any]] = await self._collect_market_pairs(chain=chain, limit_hint=limit)
        fresh_cutoff_ms = int((time.time() - 6 * 3600) * 1000)
        recent_cutoff_ms = int((time.time() - 24 * 3600) * 1000)

        fresh_tokens = []
        recent_tokens = []
        for pair in all_pairs:
            liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            created_at = pair.get("pairCreatedAt", 0) or 0
            if liquidity < 50 or created_at <= 0:
                continue
            if created_at >= fresh_cutoff_ms:
                fresh_tokens.append(pair)
            elif created_at >= recent_cutoff_ms:
                recent_tokens.append(pair)

        fresh_tokens.sort(key=lambda x: x.get("pairCreatedAt", 0) or 0, reverse=True)
        recent_tokens.sort(key=lambda x: x.get("pairCreatedAt", 0) or 0, reverse=True)

        new_tokens = fresh_tokens[:limit]
        if len(new_tokens) < limit:
            new_tokens.extend(recent_tokens[:limit - len(new_tokens)])

        logger.info(f"✅ Found {len(new_tokens)} new tokens")
        return new_tokens[:limit]

    async def search_tokens(
        self,
        query: str,
        limit: int = 10,
        chain: Optional[str] = None,
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

        normalized_chain = self._normalize_chain(chain)
        pairs = data.get("pairs", [])
        if normalized_chain:
            pairs = [p for p in pairs if self._normalize_chain(p.get("chainId")) == normalized_chain]

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
                    "chain": self._normalize_chain(pair.get("chainId")) or pair.get("chainId"),
                    "dex": pair.get("dexId", "unknown"),
                    "logo_url": pair.get("info", {}).get("imageUrl"),
                    "priceUsd": pair.get("priceUsd"),
                    "liquidity": pair.get("liquidity", {}).get("usd", 0),
                })

        return results[:limit]
