"""
Security headers middleware for FastAPI.

Adds security headers to all responses:
- Content-Security-Policy (CSP)
- X-Content-Type-Options
- X-Frame-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
- Strict-Transport-Security (HSTS)
"""

import logging
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    HTTP middleware for adding security headers.

    Configurable CSP and HSTS settings for different environments.
    """

    def __init__(
        self,
        app,
        environment: str = "development",
        csp_report_uri: Optional[str] = None,
        allowed_hosts: Optional[list[str]] = None,
    ):
        """
        Initialize security headers middleware.

        Args:
            app: FastAPI application.
            environment: Environment name (production enables HSTS).
            csp_report_uri: Optional URI for CSP violation reports.
            allowed_hosts: List of allowed hosts for connect-src directive.
        """
        super().__init__(app)
        self.environment = environment
        self.csp_report_uri = csp_report_uri
        self.allowed_hosts = allowed_hosts or []

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Add security headers to response.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/handler in chain.

        Returns:
            HTTP response with security headers.
        """
        response = await call_next(request)

        # Basic security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=()"
        )

        # Content Security Policy
        csp = self._build_csp(request)
        response.headers["Content-Security-Policy"] = csp

        # HSTS (only in production with HTTPS)
        if self.environment == "production":
            # Only add HSTS if request came via HTTPS
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
            if forwarded_proto == "https" or request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains; preload"
                )

        return response

    def _build_csp(self, request: Request) -> str:
        """
        Build Content-Security-Policy header.

        Args:
            request: HTTP request (for host-specific directives).

        Returns:
            CSP header value string.
        """
        # Get the host for WebSocket connections
        host = request.headers.get("host", "localhost")

        # Build connect-src directive
        connect_sources = ["'self'"]

        # Add WebSocket URLs
        if self.environment == "production":
            connect_sources.append(f"ws://{host}")
            connect_sources.append(f"wss://{host}")
            for allowed_host in self.allowed_hosts:
                connect_sources.append(f"ws://{allowed_host}")
                connect_sources.append(f"wss://{allowed_host}")
        else:
            # Development - allow ws:// and wss://
            connect_sources.append(f"ws://{host}")
            connect_sources.append(f"wss://{host}")
            connect_sources.append("ws://localhost:*")
            connect_sources.append("wss://localhost:*")

        directives = [
            "default-src 'self'",
            "script-src 'self'",
            # Allow inline styles for UI (cards, animations)
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            f"connect-src {' '.join(connect_sources)}",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]

        # Add report-uri if configured
        if self.csp_report_uri:
            directives.append(f"report-uri {self.csp_report_uri}")

        return "; ".join(directives)
