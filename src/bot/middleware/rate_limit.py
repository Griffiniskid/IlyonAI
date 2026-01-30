"""
Rate limiting middleware for AI Sentinel bot.

Prevents abuse by limiting requests per user.
Uses TTLCache for simple in-memory rate limiting.
"""

import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """
    Rate limiting middleware to prevent abuse.

    Limits users to a maximum number of requests per time period.
    Returns a polite message when limit is exceeded.

    Default: 10 requests per 60 seconds per user.
    """

    def __init__(
        self,
        rate_limit: int = 10,
        time_window: int = 60,
        max_users: int = 10000
    ):
        """
        Initialize rate limiter.

        Args:
            rate_limit: Maximum requests per time window
            time_window: Time window in seconds
            max_users: Maximum users to track (LRU eviction)
        """
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.cache: TTLCache = TTLCache(maxsize=max_users, ttl=time_window)
        logger.info(f"Rate limiter initialized: {rate_limit} req/{time_window}s")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Process message through rate limiter.

        Args:
            handler: Next handler in chain
            event: Telegram event (usually Message)
            data: Handler data

        Returns:
            Handler result or rate limit message
        """
        # Only rate limit messages
        if not isinstance(event, Message):
            return await handler(event, data)

        # Get user ID
        user = event.from_user
        if not user:
            return await handler(event, data)

        user_id = user.id

        # Get current request count
        current_count = self.cache.get(user_id, 0)

        # Check if rate limited
        if current_count >= self.rate_limit:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            await event.answer(
                "⚠️ <b>Слишком много запросов</b>\n\n"
                "Пожалуйста, подожди минуту перед следующим запросом.\n\n"
                "<i>Rate limit: Too many requests. Please wait a minute.</i>"
            )
            return None

        # Increment counter
        self.cache[user_id] = current_count + 1

        # Continue to handler
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    """
    Alternative throttle middleware with burst support.

    Allows short bursts but enforces overall rate limit.
    """

    def __init__(
        self,
        rate_limit: int = 20,
        time_window: int = 60,
        burst_limit: int = 5
    ):
        """
        Initialize throttle middleware.

        Args:
            rate_limit: Max requests per time window
            time_window: Time window in seconds
            burst_limit: Max burst requests (ignored for now)
        """
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.cache: TTLCache = TTLCache(maxsize=10000, ttl=time_window)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Process with throttling"""
        if not isinstance(event, Message):
            return await handler(event, data)

        user = event.from_user
        if not user:
            return await handler(event, data)

        user_id = user.id
        count = self.cache.get(user_id, 0)

        if count >= self.rate_limit:
            # Silently drop excessive requests
            return None

        self.cache[user_id] = count + 1
        return await handler(event, data)
