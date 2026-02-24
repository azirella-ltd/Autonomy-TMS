"""
Structured Logging Module
Phase 6 Sprint 3: Monitoring & Observability

Provides:
- Correlation ID middleware for request tracing
- JSON-formatted structured logging
- Context management for log enrichment
- Performance timing decorators
- Request/response logging
"""

import logging
import json
import time
import uuid
import sys
from datetime import datetime
from typing import Any, Dict, Optional, Callable
from functools import wraps
from contextvars import ContextVar
from pathlib import Path

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Context variable for correlation ID
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

# Context variable for additional log context
log_context_ctx: ContextVar[Dict[str, Any]] = ContextVar('log_context', default={})


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging

    Produces logs in the format:
    {
        "timestamp": "2026-01-13T10:30:45.123Z",
        "level": "INFO",
        "correlation_id": "req-abc123",
        "logger": "app.api.endpoints.game",
        "message": "Game created",
        "context": {...},
        "exception": {...}
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        # Base log data
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        # Add correlation ID if available
        correlation_id = correlation_id_ctx.get()
        if correlation_id:
            log_data['correlation_id'] = correlation_id

        # Add log context if available
        context = log_context_ctx.get()
        if context:
            log_data['context'] = context.copy()

        # Add extra fields from record
        if hasattr(record, 'context'):
            if 'context' not in log_data:
                log_data['context'] = {}
            log_data['context'].update(record.context)

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }

        # Add source location
        log_data['source'] = {
            'file': record.pathname,
            'line': record.lineno,
            'function': record.funcName
        }

        return json.dumps(log_data)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject correlation IDs into requests

    Creates a unique correlation ID for each request and makes it
    available throughout the request lifecycle via context variables.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = get_logger(__name__)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and inject correlation ID"""
        # Get or generate correlation ID
        correlation_id = request.headers.get('X-Correlation-ID')
        if not correlation_id:
            correlation_id = f"req-{uuid.uuid4().hex[:12]}"

        # Set in context
        correlation_id_ctx.set(correlation_id)

        # Log request start
        start_time = time.time()
        self.logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                'context': {
                    'method': request.method,
                    'path': request.url.path,
                    'query_params': str(request.query_params),
                    'client_ip': request.client.host if request.client else None,
                    'user_agent': request.headers.get('user-agent')
                }
            }
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log request completion
            self.logger.info(
                f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                extra={
                    'context': {
                        'method': request.method,
                        'path': request.url.path,
                        'status_code': response.status_code,
                        'duration_ms': round(duration_ms, 2)
                    }
                }
            )

            # Add correlation ID to response headers
            response.headers['X-Correlation-ID'] = correlation_id

            return response

        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    'context': {
                        'method': request.method,
                        'path': request.url.path,
                        'error': str(e),
                        'duration_ms': round(duration_ms, 2)
                    }
                },
                exc_info=True
            )
            raise


class LogContext:
    """
    Context manager for adding temporary context to logs

    Usage:
        with LogContext(user_id=42, scenario_id=123):
            logger.info("Game action")  # Will include user_id and scenario_id
    """

    def __init__(self, **context):
        self.context = context
        self.token = None

    def __enter__(self):
        current_context = log_context_ctx.get().copy()
        current_context.update(self.context)
        self.token = log_context_ctx.set(current_context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        log_context_ctx.reset(self.token)


def timed(metric_name: Optional[str] = None):
    """
    Decorator to time function execution and log performance

    Usage:
        @timed("game_creation")
        def create_game(...):
            ...

    Args:
        metric_name: Name for the metric (defaults to function name)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            logger = get_logger(func.__module__)
            name = metric_name or func.__name__

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start) * 1000
                logger.info(
                    f"Function executed: {name}",
                    extra={
                        'context': {
                            'function': name,
                            'duration_ms': round(duration_ms, 2),
                            'status': 'success'
                        }
                    }
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                logger.error(
                    f"Function failed: {name}",
                    extra={
                        'context': {
                            'function': name,
                            'duration_ms': round(duration_ms, 2),
                            'status': 'error',
                            'error': str(e)
                        }
                    },
                    exc_info=True
                )
                raise

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            logger = get_logger(func.__module__)
            name = metric_name or func.__name__

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start) * 1000
                logger.info(
                    f"Async function executed: {name}",
                    extra={
                        'context': {
                            'function': name,
                            'duration_ms': round(duration_ms, 2),
                            'status': 'success'
                        }
                    }
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                logger.error(
                    f"Async function failed: {name}",
                    extra={
                        'context': {
                            'function': name,
                            'duration_ms': round(duration_ms, 2),
                            'status': 'error',
                            'error': str(e)
                        }
                    },
                    exc_info=True
                )
                raise

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class PerformanceTimer:
    """
    Context manager for timing code blocks

    Usage:
        with PerformanceTimer("database_query") as timer:
            result = db.query(...)
        # Automatically logs duration
    """

    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None):
        self.operation_name = operation_name
        self.logger = logger or get_logger(__name__)
        self.start_time = None
        self.duration_ms = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration_ms = (time.time() - self.start_time) * 1000

        if exc_type is None:
            self.logger.info(
                f"Operation completed: {self.operation_name}",
                extra={
                    'context': {
                        'operation': self.operation_name,
                        'duration_ms': round(self.duration_ms, 2)
                    }
                }
            )
        else:
            self.logger.error(
                f"Operation failed: {self.operation_name}",
                extra={
                    'context': {
                        'operation': self.operation_name,
                        'duration_ms': round(self.duration_ms, 2),
                        'error': str(exc_val)
                    }
                },
                exc_info=(exc_type, exc_val, exc_tb)
            )


def setup_logging(
    log_level: str = 'INFO',
    log_file: Optional[Path] = None,
    json_format: bool = True
) -> None:
    """
    Configure application logging

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (if None, logs to stdout only)
        json_format: Use JSON formatter (True) or standard formatter (False)
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set library loggers to WARNING to reduce noise
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID from context"""
    return correlation_id_ctx.get()


def set_log_context(**context):
    """
    Add context to all logs in the current scope

    Args:
        **context: Key-value pairs to add to log context
    """
    current_context = log_context_ctx.get().copy()
    current_context.update(context)
    log_context_ctx.set(current_context)


def clear_log_context():
    """Clear all log context"""
    log_context_ctx.set({})


# Example usage
if __name__ == '__main__':
    # Setup logging
    setup_logging(log_level='INFO', json_format=True)

    logger = get_logger(__name__)

    # Simulate request with correlation ID
    correlation_id_ctx.set('test-req-123')

    # Basic logging
    logger.info("Application started")

    # Logging with context
    with LogContext(user_id=42, scenario_id=100):
        logger.info("User action performed")
        logger.warning("Potential issue detected")

    # Logging with explicit context
    logger.info(
        "Game created",
        extra={
            'context': {
                'scenario_id': 100,
                'player_count': 4,
                'config': 'Default Supply Chain'
            }
        }
    )

    # Timed function
    @timed("example_operation")
    def example_function():
        time.sleep(0.1)
        return "done"

    result = example_function()

    # Performance timer
    with PerformanceTimer("database_operation", logger):
        time.sleep(0.05)

    # Error logging
    try:
        raise ValueError("Example error")
    except Exception as e:
        logger.error("Error occurred", exc_info=True)

    print("\n✅ Structured logging demo complete")
    print("Check logs for JSON-formatted output with correlation IDs")
