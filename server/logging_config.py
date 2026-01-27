"""
Structured logging configuration for Golf game server.

Provides:
- JSONFormatter for production (machine-readable logs)
- Human-readable formatter for development
- Contextual logging (request_id, user_id, game_id)
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

# Context variables for request-scoped data
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
game_id_var: ContextVar[Optional[str]] = ContextVar("game_id", default=None)


class JSONFormatter(logging.Formatter):
    """
    Format logs as JSON for production log aggregation.

    Output format is compatible with common log aggregation systems
    (ELK, CloudWatch, Datadog, etc.).
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context from context variables
        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id

        user_id = user_id_var.get()
        if user_id:
            log_data["user_id"] = user_id

        game_id = game_id_var.get()
        if game_id:
            log_data["game_id"] = game_id

        # Add extra fields from record
        if hasattr(record, "request_id") and record.request_id:
            log_data["request_id"] = record.request_id
        if hasattr(record, "user_id") and record.user_id:
            log_data["user_id"] = record.user_id
        if hasattr(record, "game_id") and record.game_id:
            log_data["game_id"] = record.game_id
        if hasattr(record, "room_code") and record.room_code:
            log_data["room_code"] = record.room_code
        if hasattr(record, "player_id") and record.player_id:
            log_data["player_id"] = record.player_id

        # Add source location for errors
        if record.levelno >= logging.ERROR:
            log_data["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class DevelopmentFormatter(logging.Formatter):
    """
    Human-readable formatter for development.

    Includes colors and context for easy debugging.
    """

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with colors and context.

        Args:
            record: Log record to format.

        Returns:
            Formatted log string.
        """
        # Get color for level
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""

        # Build timestamp
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Build context string
        context_parts = []
        request_id = request_id_var.get() or getattr(record, "request_id", None)
        if request_id:
            context_parts.append(f"req={request_id[:8]}")

        user_id = user_id_var.get() or getattr(record, "user_id", None)
        if user_id:
            context_parts.append(f"user={user_id[:8]}")

        room_code = getattr(record, "room_code", None)
        if room_code:
            context_parts.append(f"room={room_code}")

        context = f" [{', '.join(context_parts)}]" if context_parts else ""

        # Format message
        message = record.getMessage()

        # Build final output
        output = f"{timestamp} {color}{record.levelname:8}{reset} {record.name}{context} - {message}"

        # Add exception if present
        if record.exc_info:
            output += "\n" + self.formatException(record.exc_info)

        return output


def setup_logging(
    level: str = "INFO",
    environment: str = "development",
) -> None:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        environment: Environment name (production uses JSON, else human-readable).
    """
    # Get log level
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    # Choose formatter based on environment
    if environment == "production":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(DevelopmentFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Log startup
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured: level={level}, environment={environment}",
        extra={"level": level, "environment": environment},
    )


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes context.

    Usage:
        logger = ContextLogger(logging.getLogger(__name__))
        logger.with_context(room_code="ABCD", player_id="123").info("Player joined")
    """

    def __init__(self, logger: logging.Logger, extra: Optional[dict] = None):
        """
        Initialize context logger.

        Args:
            logger: Base logger instance.
            extra: Extra context to include in all messages.
        """
        super().__init__(logger, extra or {})

    def with_context(self, **kwargs) -> "ContextLogger":
        """
        Create a new logger with additional context.

        Args:
            **kwargs: Context key-value pairs to add.

        Returns:
            New ContextLogger with combined context.
        """
        new_extra = {**self.extra, **kwargs}
        return ContextLogger(self.logger, new_extra)

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        """
        Process log message to include context.

        Args:
            msg: Log message.
            kwargs: Keyword arguments.

        Returns:
            Processed message and kwargs.
        """
        # Merge extra into kwargs
        kwargs["extra"] = {**self.extra, **kwargs.get("extra", {})}
        return msg, kwargs


def get_logger(name: str) -> ContextLogger:
    """
    Get a context-aware logger.

    Args:
        name: Logger name (typically __name__).

    Returns:
        ContextLogger instance.
    """
    return ContextLogger(logging.getLogger(name))
