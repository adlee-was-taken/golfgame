"""
Rate limiting middleware for FastAPI.

Applies per-endpoint rate limits and adds X-RateLimit-* headers to responses.
"""

import logging
from typing import Callable, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from services.ratelimit import RateLimiter, RATE_LIMITS

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    HTTP middleware for rate limiting API requests.

    Applies rate limits based on request path and adds standard
    rate limit headers to all responses.
    """

    def __init__(
        self,
        app,
        rate_limiter: RateLimiter,
        enabled: bool = True,
        get_user_id: Optional[Callable[[Request], Optional[str]]] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application.
            rate_limiter: RateLimiter service instance.
            enabled: Whether rate limiting is enabled.
            get_user_id: Optional callback to extract user ID from request.
        """
        super().__init__(app)
        self.limiter = rate_limiter
        self.enabled = enabled
        self.get_user_id = get_user_id

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request through rate limiter.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/handler in chain.

        Returns:
            HTTP response with rate limit headers.
        """
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Determine rate limit tier based on path
        path = request.url.path
        limit_config = self._get_limit_config(path, request.method)

        # No rate limiting for this endpoint
        if limit_config is None:
            return await call_next(request)

        limit, window = limit_config

        # Get user ID if authenticated
        user_id = None
        if self.get_user_id:
            try:
                user_id = self.get_user_id(request)
            except Exception:
                pass

        # Generate client key
        client_key = self.limiter.get_client_key(request, user_id)

        # Check rate limit
        endpoint_key = self._get_endpoint_key(path)
        full_key = f"{endpoint_key}:{client_key}"

        allowed, info = await self.limiter.is_allowed(full_key, limit, window)

        # Build response
        if allowed:
            response = await call_next(request)
        else:
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Please wait {info['reset']} seconds.",
                    "retry_after": info["reset"],
                },
            )

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        if not allowed:
            response.headers["Retry-After"] = str(info["reset"])

        return response

    def _get_limit_config(
        self,
        path: str,
        method: str,
    ) -> Optional[tuple[int, int]]:
        """
        Get rate limit configuration for a path.

        Args:
            path: Request URL path.
            method: HTTP method.

        Returns:
            Tuple of (limit, window_seconds) or None for no limiting.
        """
        # No rate limiting for health checks
        if path in ("/health", "/ready", "/metrics"):
            return None

        # No rate limiting for static files
        if path.endswith((".js", ".css", ".html", ".ico", ".png", ".jpg")):
            return None

        # Authentication endpoints - stricter limits
        if path.startswith("/api/auth"):
            return RATE_LIMITS["api_auth"]

        # Room creation - moderate limits
        if path == "/api/rooms" and method == "POST":
            return RATE_LIMITS["api_create_room"]

        # Email endpoints - very strict
        if "email" in path or "verify" in path:
            return RATE_LIMITS["email_send"]

        # General API endpoints
        if path.startswith("/api"):
            return RATE_LIMITS["api_general"]

        # Default: no rate limiting for non-API paths
        return None

    def _get_endpoint_key(self, path: str) -> str:
        """
        Normalize path to endpoint key for rate limiting.

        Groups similar endpoints together (e.g., /api/users/123 -> /api/users/:id).

        Args:
            path: Request URL path.

        Returns:
            Normalized endpoint key.
        """
        # Simple normalization - strip trailing slashes
        key = path.rstrip("/")

        # Could add more sophisticated path parameter normalization here
        # For example: /api/users/123 -> /api/users/:id

        return key or "/"
