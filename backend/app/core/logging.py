"""Structured logging configuration."""
import logging
import sys
from typing import Any, Dict
import structlog
from app.core.config import settings


def setup_logging() -> None:
    """Configure structured logging with structlog."""
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.log_level == "DEBUG" 
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """Bind context variables to logger."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**kwargs)


def log_request(request_id: str, method: str, path: str, **extra: Any) -> None:
    """Log an incoming request."""
    logger = get_logger("api.request")
    logger.info(
        "request_started",
        request_id=request_id,
        method=method,
        path=path,
        **extra
    )


def log_response(request_id: str, status_code: int, duration_ms: float, **extra: Any) -> None:
    """Log an outgoing response."""
    logger = get_logger("api.response")
    logger.info(
        "request_completed",
        request_id=request_id,
        status_code=status_code,
        duration_ms=duration_ms,
        **extra
    )


