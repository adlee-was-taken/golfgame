"""
Redis-based rate limiter service.

Implements a sliding window counter algorithm using Redis for distributed
rate limiting across multiple server instances.
"""

import hashlib
import logging
import time
from typing import Optional

import redis.asyncio as redis
from fastapi import Request, WebSocket

logger = logging.getLogger(__name__)


# Rate limit configurations: (max_requests, window_seconds)
RATE_LIMITS = {
    "api_general": (100, 60),       # 100 requests per minute
    "api_auth": (10, 60),           # 10 auth attempts per minute
    "api_create_room": (5, 60),     # 5 room creations per minute
    "websocket_connect": (10, 60),  # 10 WS connections per minute
    "websocket_message": (30, 10),  # 30 messages per 10 seconds
    "email_send": (3, 300),         # 3 emails per 5 minutes
}


class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize rate limiter with Redis client.

        Args:
            redis_client: Async Redis client for state storage.
        """
        self.redis = redis_client

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, dict]:
        """
        Check if request is allowed under rate limit.

        Uses a sliding window counter algorithm:
        - Divides time into fixed windows
        - Counts requests in current window
        - Atomically increments and checks limit

        Args:
            key: Unique identifier for the rate limit bucket.
            limit: Maximum requests allowed in window.
            window_seconds: Time window in seconds.

        Returns:
            Tuple of (allowed, info) where info contains:
            - remaining: requests remaining in window
            - reset: seconds until window resets
            - limit: the limit that was applied
        """
        now = int(time.time())
        window_key = f"ratelimit:{key}:{now // window_seconds}"

        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(window_key)
                pipe.expire(window_key, window_seconds + 1)  # Extra second for safety
                results = await pipe.execute()

            current_count = results[0]
            remaining = max(0, limit - current_count)
            reset = window_seconds - (now % window_seconds)

            info = {
                "remaining": remaining,
                "reset": reset,
                "limit": limit,
            }

            allowed = current_count <= limit
            if not allowed:
                logger.warning(f"Rate limit exceeded for {key}: {current_count}/{limit}")

            return allowed, info

        except redis.RedisError as e:
            # If Redis is unavailable, fail open (allow request)
            logger.error(f"Rate limiter Redis error: {e}")
            return True, {"remaining": limit, "reset": window_seconds, "limit": limit}

    def get_client_key(
        self,
        request: Request | WebSocket,
        user_id: Optional[str] = None,
    ) -> str:
        """
        Generate rate limit key for client.

        Uses user ID if authenticated, otherwise hashes client IP.

        Args:
            request: HTTP request or WebSocket.
            user_id: Authenticated user ID, if available.

        Returns:
            Unique client identifier string.
        """
        if user_id:
            return f"user:{user_id}"

        # For anonymous users, use IP hash
        client_ip = self._get_client_ip(request)

        # Hash IP for privacy
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]
        return f"ip:{ip_hash}"

    def _get_client_ip(self, request: Request | WebSocket) -> str:
        """
        Extract client IP from request, handling proxies.

        Args:
            request: HTTP request or WebSocket.

        Returns:
            Client IP address string.
        """
        # Check X-Forwarded-For header (from reverse proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP (original client)
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header (nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct connection
        if request.client:
            return request.client.host

        return "unknown"


class ConnectionMessageLimiter:
    """
    In-memory rate limiter for WebSocket message frequency.

    Used to limit messages within a single connection without
    requiring Redis round-trips for every message.
    """

    def __init__(self, max_messages: int = 30, window_seconds: int = 10):
        """
        Initialize connection message limiter.

        Args:
            max_messages: Maximum messages allowed in window.
            window_seconds: Time window in seconds.
        """
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self.timestamps: list[float] = []

    def check(self) -> bool:
        """
        Check if another message is allowed.

        Maintains a sliding window of message timestamps.

        Returns:
            True if message is allowed, False if rate limited.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Remove old timestamps
        self.timestamps = [t for t in self.timestamps if t > cutoff]

        # Check limit
        if len(self.timestamps) >= self.max_messages:
            return False

        # Record this message
        self.timestamps.append(now)
        return True

    def reset(self):
        """Reset the limiter (e.g., on reconnection)."""
        self.timestamps = []


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter(redis_client: redis.Redis) -> RateLimiter:
    """
    Get or create the global rate limiter instance.

    Args:
        redis_client: Redis client for state storage.

    Returns:
        RateLimiter instance.
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(redis_client)
    return _rate_limiter


def close_rate_limiter():
    """Close the global rate limiter."""
    global _rate_limiter
    _rate_limiter = None
