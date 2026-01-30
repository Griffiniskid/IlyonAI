"""
Bot middleware for AI Sentinel.

Provides rate limiting and other request processing.
"""

from src.bot.middleware.rate_limit import RateLimitMiddleware

__all__ = ["RateLimitMiddleware"]
