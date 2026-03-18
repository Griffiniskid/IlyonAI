"""
Caching layer for Ilyon AI.

Provides Redis-based caching with in-memory fallback.
Caches token analysis results to reduce API calls and improve response times.
"""

import json
import logging
from typing import Optional, Any, Dict
from collections import OrderedDict
import time

from src.config import settings

logger = logging.getLogger(__name__)

# Try to import Redis
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.info("Redis not installed - using memory cache only")


# ═══════════════════════════════════════════════════════════════════════════════
# CACHE INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

class CacheLayer:
    """
    Production-ready cache with Redis and in-memory fallback.

    Features:
    - Redis primary cache when REDIS_URL configured
    - TTLCache fallback for development/simple deployments
    - Async operations for non-blocking performance
    - JSON serialization for complex objects
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl: int = 120,
        max_memory_items: int = 1000
    ):
        """
        Initialize cache layer.

        Args:
            redis_url: Redis connection URL (optional)
            ttl: Default TTL in seconds
            max_memory_items: Max items in memory cache
        """
        self.ttl = ttl
        self.max_memory_items = max_memory_items
        self.redis_client: Optional[redis.Redis] = None
        self.redis_connected = False

        # In-memory fallback cache
        self._memory_cache: OrderedDict[str, Any] = OrderedDict()
        self._memory_expiry: Dict[str, float] = {}

        # Try to connect to Redis
        url = redis_url or settings.redis_url
        if url and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(
                    url,
                    encoding="utf-8",
                    decode_responses=True
                )
                logger.info(f"Redis cache configured: {url.split('@')[-1]}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self.redis_client = None

    async def _check_redis(self) -> bool:
        """Check if Redis is connected"""
        if self.redis_client and not self.redis_connected:
            try:
                await self.redis_client.ping()
                self.redis_connected = True
                logger.info("✅ Redis connection verified")
            except Exception as e:
                logger.warning(f"Redis ping failed: {e}")
                self.redis_connected = False
        return self.redis_connected

    def _serialize(self, value: Any) -> str:
        """Serialize value for storage"""
        if isinstance(value, str):
            return value
        return json.dumps(value, default=str)

    def _deserialize(self, value: str) -> Any:
        """Deserialize value from storage"""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def _purge_expired_memory_keys(self) -> None:
        now = time.monotonic()
        expired_keys = [key for key, expires_at in self._memory_expiry.items() if expires_at <= now]
        for key in expired_keys:
            self._memory_cache.pop(key, None)
            self._memory_expiry.pop(key, None)

    def _memory_get(self, key: str) -> Optional[Any]:
        self._purge_expired_memory_keys()
        value = self._memory_cache.get(key)
        if value is not None:
            self._memory_cache.move_to_end(key)
        return value

    def _memory_set(self, key: str, value: Any, ttl: float) -> None:
        self._purge_expired_memory_keys()
        self._memory_cache[key] = value
        self._memory_cache.move_to_end(key)
        self._memory_expiry[key] = time.monotonic() + ttl

        while len(self._memory_cache) > self.max_memory_items:
            oldest_key, _ = self._memory_cache.popitem(last=False)
            self._memory_expiry.pop(oldest_key, None)

    def _memory_delete(self, key: str) -> None:
        self._memory_cache.pop(key, None)
        self._memory_expiry.pop(key, None)

    # ═══════════════════════════════════════════════════════════════════════════
    # CORE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get(self, key: str) -> Optional[Any]:
        """
        Get cached value.

        Tries Redis first, falls back to memory cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        # Try Redis
        if await self._check_redis():
            try:
                value = await self.redis_client.get(key)
                if value is not None:
                    return self._deserialize(value)
            except Exception as e:
                logger.debug(f"Redis get error: {e}")

        # Fallback to memory
        return self._memory_get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set cached value.

        Stores in both Redis and memory for redundancy.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override

        Returns:
            True if successfully cached
        """
        ttl = ttl or self.ttl

        # Store in memory first (always works)
        try:
            self._memory_set(key, value, ttl)
        except Exception as e:
            logger.debug(f"Memory cache set error: {e}")

        # Try Redis
        if await self._check_redis():
            try:
                serialized = self._serialize(value)
                await self.redis_client.setex(key, ttl, serialized)
                return True
            except Exception as e:
                logger.debug(f"Redis set error: {e}")

        return True  # Memory cache succeeded

    async def delete(self, key: str) -> bool:
        """
        Delete cached value.

        Args:
            key: Cache key

        Returns:
            True if deleted
        """
        # Delete from memory
        self._memory_delete(key)

        # Delete from Redis
        if await self._check_redis():
            try:
                await self.redis_client.delete(key)
            except Exception as e:
                logger.debug(f"Redis delete error: {e}")

        return True

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        # Check Redis first
        if await self._check_redis():
            try:
                return await self.redis_client.exists(key) > 0
            except Exception:
                pass

        # Check memory
        self._purge_expired_memory_keys()
        return key in self._memory_cache

    async def clear(self) -> bool:
        """Clear all cached values"""
        # Clear memory
        self._memory_cache.clear()
        self._memory_expiry.clear()

        # Clear Redis (be careful in production!)
        if await self._check_redis():
            try:
                await self.redis_client.flushdb()
            except Exception as e:
                logger.warning(f"Redis flush error: {e}")

        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # ANALYSIS CACHING
    # ═══════════════════════════════════════════════════════════════════════════

    def _analysis_key(self, token_address: str) -> str:
        """Generate cache key for token analysis"""
        return f"analysis:{token_address[:16]}"

    async def get_analysis(self, token_address: str) -> Optional[Dict]:
        """
        Get cached token analysis result.

        Args:
            token_address: Solana token address

        Returns:
            Cached analysis dict or None
        """
        key = self._analysis_key(token_address)
        result = await self.get(key)

        if result:
            logger.debug(f"Cache HIT: {token_address[:8]}...")
        else:
            logger.debug(f"Cache MISS: {token_address[:8]}...")

        return result

    async def set_analysis(
        self,
        token_address: str,
        result: Dict,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache token analysis result.

        Args:
            token_address: Solana token address
            result: Analysis result dict
            ttl: Optional TTL override

        Returns:
            True if cached
        """
        key = self._analysis_key(token_address)
        success = await self.set(key, result, ttl)

        if success:
            logger.debug(f"Cached analysis: {token_address[:8]}... (TTL: {ttl or self.ttl}s)")

        return success

    async def invalidate_analysis(self, token_address: str) -> bool:
        """
        Invalidate cached analysis (e.g., on refresh).

        Args:
            token_address: Solana token address

        Returns:
            True if invalidated
        """
        key = self._analysis_key(token_address)
        await self.delete(key)
        logger.debug(f"Cache invalidated: {token_address[:8]}...")
        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # RATE LIMITING SUPPORT
    # ═══════════════════════════════════════════════════════════════════════════

    async def increment(self, key: str, ttl: int = 60) -> int:
        """
        Increment counter (for rate limiting).

        Args:
            key: Counter key
            ttl: TTL for counter

        Returns:
            New counter value
        """
        # Try Redis (atomic increment)
        if await self._check_redis():
            try:
                pipe = self.redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, ttl)
                results = await pipe.execute()
                return results[0]
            except Exception as e:
                logger.debug(f"Redis increment error: {e}")

        # Fallback to memory (not atomic but works)
        count = (self._memory_get(key) or 0) + 1
        self._memory_set(key, count, ttl)
        return count

    # ═══════════════════════════════════════════════════════════════════════════
    # STATS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        stats = {
            "memory_items": len(self._memory_cache),
            "memory_maxsize": self._memory_cache.maxsize,
            "redis_connected": self.redis_connected,
            "ttl": self.ttl
        }

        if await self._check_redis():
            try:
                info = await self.redis_client.info("memory")
                stats["redis_memory"] = info.get("used_memory_human", "N/A")
            except Exception:
                pass

        return stats

    async def close(self):
        """Close cache connections"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL CACHE INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_cache: Optional[CacheLayer] = None


CacheManager = CacheLayer


def get_cache() -> CacheLayer:
    """Get or create global cache instance"""
    global _cache
    if _cache is None:
        _cache = CacheLayer(
            redis_url=settings.redis_url,
            ttl=settings.cache_ttl_seconds
        )
    return _cache


async def init_cache() -> CacheLayer:
    """Initialize cache at startup"""
    cache = get_cache()
    # Verify connection
    await cache._check_redis()
    return cache
