"""
Request ID middleware for request tracing.

Generates or propagates X-Request-ID header for distributed tracing.
"""

import logging
import uuid
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from logging_config import request_id_var

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    HTTP middleware for request ID generation and propagation.

    - Extracts X-Request-ID from incoming request headers
    - Generates a new UUID if not present
    - Sets request_id in context var for logging
    - Adds X-Request-ID to response headers
    """

    def __init__(
        self,
        app,
        header_name: str = "X-Request-ID",
        generator: Optional[callable] = None,
    ):
        """
        Initialize request ID middleware.

        Args:
            app: FastAPI application.
            header_name: Header name for request ID.
            generator: Optional custom ID generator function.
        """
        super().__init__(app)
        self.header_name = header_name
        self.generator = generator or (lambda: str(uuid.uuid4()))

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request with request ID.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/handler in chain.

        Returns:
            HTTP response with X-Request-ID header.
        """
        # Get or generate request ID
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = self.generator()

        # Set in request state for access in handlers
        request.state.request_id = request_id

        # Set in context var for logging
        token = request_id_var.set(request_id)

        try:
            # Process request
            response = await call_next(request)

            # Add request ID to response
            response.headers[self.header_name] = request_id

            return response
        finally:
            # Reset context var
            request_id_var.reset(token)


def get_request_id(request: Request) -> Optional[str]:
    """
    Get request ID from request state.

    Args:
        request: FastAPI request object.

    Returns:
        Request ID string or None.
    """
    return getattr(request.state, "request_id", None)
