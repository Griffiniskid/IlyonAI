"""
Rate limiting middleware for Solana Actions API.

Prevents abuse while allowing legitimate unfurling and verification.
"""

import logging
import hashlib
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple
from aiohttp import web
from aiohttp.web import middleware

from src.config import settings

logger = logging.getLogger(__name__)


def rate_limit_scope_for_path(path: str, method: str) -> str:
    """Classify the request path for lightweight rate-limit observability."""
    if path.startswith("/api/v1/alerts/rules") and method in {"POST", "PUT", "DELETE"}:
        return "alerts_rules_mutation"
    if path.startswith("/api/v1/stream/"):
        return "stream"
    if path.startswith("/opportunities"):
        return "opportunities"
    return "default"


class RateLimiter:
    """
    In-memory rate limiter with sliding window.

    Tracks request counts per IP with configurable limits.
    """

    def __init__(
        self,
        requests_per_minute: int = 30,
        requests_per_hour: int = 200,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

        # Track requests: ip_hash -> [(timestamp, ...)]
        self._minute_requests: Dict[str, list] = defaultdict(list)
        self._hour_requests: Dict[str, list] = defaultdict(list)

        # Last cleanup time
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # seconds

    def _hash_ip(self, ip: str) -> str:
        """Hash IP for privacy"""
        return hashlib.sha256(ip.encode()).hexdigest()[:16]

    def _cleanup_old_requests(self):
        """Remove expired request records"""
        now = time.time()

        if now - self._last_cleanup < self._cleanup_interval:
            return

        minute_ago = now - 60
        hour_ago = now - 3600

        # Cleanup minute requests
        for ip_hash in list(self._minute_requests.keys()):
            self._minute_requests[ip_hash] = [
                ts for ts in self._minute_requests[ip_hash] if ts > minute_ago
            ]
            if not self._minute_requests[ip_hash]:
                del self._minute_requests[ip_hash]

        # Cleanup hour requests
        for ip_hash in list(self._hour_requests.keys()):
            self._hour_requests[ip_hash] = [
                ts for ts in self._hour_requests[ip_hash] if ts > hour_ago
            ]
            if not self._hour_requests[ip_hash]:
                del self._hour_requests[ip_hash]

        self._last_cleanup = now

    def check_rate_limit(self, ip: str) -> Tuple[bool, str, Optional[int]]:
        """
        Check if request should be allowed.

        Args:
            ip: Client IP address

        Returns:
            Tuple of (allowed, reason, reset_epoch_seconds)
        """
        self._cleanup_old_requests()

        now = time.time()
        ip_hash = self._hash_ip(ip)

        minute_ago = now - 60
        hour_ago = now - 3600

        # Count recent requests
        minute_count = sum(
            1 for ts in self._minute_requests[ip_hash] if ts > minute_ago
        )
        hour_count = sum(
            1 for ts in self._hour_requests[ip_hash] if ts > hour_ago
        )

        # Check limits
        if minute_count >= self.requests_per_minute:
            minute_timestamps = [ts for ts in self._minute_requests[ip_hash] if ts > minute_ago]
            reset_at = int(min(minute_timestamps) + 60) if minute_timestamps else int(now + 60)
            return False, f"Rate limit exceeded: {self.requests_per_minute}/minute", reset_at

        if hour_count >= self.requests_per_hour:
            hour_timestamps = [ts for ts in self._hour_requests[ip_hash] if ts > hour_ago]
            reset_at = int(min(hour_timestamps) + 3600) if hour_timestamps else int(now + 3600)
            return False, f"Rate limit exceeded: {self.requests_per_hour}/hour", reset_at

        # Record this request
        self._minute_requests[ip_hash].append(now)
        self._hour_requests[ip_hash].append(now)

        return True, "", None

    def get_ip_hash(self, ip: str) -> str:
        """Get hashed IP for analytics"""
        return self._hash_ip(ip)


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None
_authenticated_rate_limiter: RateLimiter | None = None
_scope_burst_limit_per_minute = settings.scope_burst_limit_per_minute
_scope_burst_requests: Dict[str, list[float]] = defaultdict(list)


def _check_scope_burst_limit(scope: str, key: str) -> Tuple[bool, Optional[int]]:
    if scope == "default":
        return True, None

    now = time.time()
    minute_ago = now - 60
    bucket_key = f"{scope}:{key}"
    timestamps = [ts for ts in _scope_burst_requests[bucket_key] if ts > minute_ago]
    _scope_burst_requests[bucket_key] = timestamps

    if len(timestamps) >= _scope_burst_limit_per_minute:
        reset_at = int(min(timestamps) + 60) if timestamps else int(now + 60)
        return False, reset_at

    _scope_burst_requests[bucket_key].append(now)
    return True, None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            requests_per_minute=settings.blinks_rate_limit_per_minute,
            requests_per_hour=settings.blinks_rate_limit_per_hour,
        )
    return _rate_limiter


def get_authenticated_rate_limiter() -> RateLimiter:
    """Get or create global authenticated rate limiter."""
    global _authenticated_rate_limiter
    if _authenticated_rate_limiter is None:
        _authenticated_rate_limiter = RateLimiter(
            requests_per_minute=settings.blinks_rate_limit_per_minute * 2,
            requests_per_hour=settings.blinks_rate_limit_per_hour * 2,
        )
    return _authenticated_rate_limiter


@middleware
async def rate_limit_middleware(request: web.Request, handler):
    """
    Rate limiting middleware.
    
    Returns 429 Too Many Requests if limit exceeded.
    Tracks by IP for anonymous users, by wallet for authenticated users.
    Authenticated users get higher limits.
    """
    # Skip rate limiting for OPTIONS requests
    if request.method == "OPTIONS":
        return await handler(request)

    # Skip for health check
    if request.path == "/health":
        return await handler(request)

    request["rate_limit_scope"] = rate_limit_scope_for_path(request.path, request.method)

    # Get client IP
    ip = request.headers.get("X-Forwarded-For") or request.remote or "unknown"
    if "," in ip:
        ip = ip.split(",")[0].strip()

    # Check for authenticated user (added by auth middleware)
    user_wallet = request.get('user_wallet')
    
    # Use wallet address as rate limit key if authenticated
    # Authenticated users get 2x the rate limits
    limiter = get_rate_limiter()
    
    if user_wallet:
        auth_limiter = get_authenticated_rate_limiter()
        allowed, reason, reset_at = auth_limiter.check_rate_limit(user_wallet)
        request["rate_limit_key"] = f"wallet:{user_wallet[:8]}"
    else:
        # For anonymous users, use IP
        allowed, reason, reset_at = limiter.check_rate_limit(ip)
        request["rate_limit_key"] = f"ip:{limiter.get_ip_hash(ip)}"

    scope_allowed, scope_reset_at = _check_scope_burst_limit(
        request.get("rate_limit_scope", "default"),
        request.get("rate_limit_key", "unknown"),
    )
    if not scope_allowed:
        allowed = False
        reason = (
            f"Scope burst rate limit exceeded: "
            f"{_scope_burst_limit_per_minute}/minute for {request.get('rate_limit_scope', 'default')}"
        )
        reset_at = scope_reset_at

    if not allowed:
        reset_at = reset_at or int(time.time() + 60)
        retry_after = max(1, reset_at - int(time.time()))
        logger.warning(f"Rate limit exceeded for {request.get('rate_limit_key', 'unknown')}: {reason}")
        return web.json_response(
            {"error": reason, "code": "RATE_LIMIT_EXCEEDED"},
            status=429,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Retry-After": str(retry_after),
                "X-RateLimit-Reset": str(reset_at),
            },
        )

    # Store IP hash in request for analytics
    request["ip_hash"] = limiter.get_ip_hash(ip)

    return await handler(request)
