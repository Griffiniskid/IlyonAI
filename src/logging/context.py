"""
Logging context management for request tracing.

Provides:
- Trace ID generation and propagation
- Context managers for request tracking
- Structured context data
"""

import time
import logging
from contextvars import ContextVar
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


# Context variables for async operations
_trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
_user_id_var: ContextVar[Optional[int]] = ContextVar('user_id', default=None)
_symbol_var: ContextVar[Optional[str]] = ContextVar('symbol', default=None)


def generate_trace_id(symbol: str = "UNKNOWN", operation: str = "op") -> str:
    """
    Generate a unique trace ID for request tracking.

    Format: {symbol}_{operation}_{timestamp_ms}

    Args:
        symbol: Token symbol or identifier
        operation: Operation name (e.g., 'analyze', 'chat')

    Returns:
        Unique trace ID string

    Example:
        >>> generate_trace_id("BONK", "analyze")
        'BONK_analyze_1735564496789'
    """
    timestamp_ms = int(time.time() * 1000)
    return f"{symbol}_{operation}_{timestamp_ms}"


def set_trace_id(trace_id: str):
    """
    Set trace ID in current context.

    Args:
        trace_id: Trace ID to set
    """
    _trace_id_var.set(trace_id)


def get_trace_id() -> Optional[str]:
    """
    Get trace ID from current context.

    Returns:
        Current trace ID or None
    """
    return _trace_id_var.get()


def set_user_id(user_id: int):
    """
    Set user ID in current context.

    Args:
        user_id: User ID to set
    """
    _user_id_var.set(user_id)


def get_user_id() -> Optional[int]:
    """
    Get user ID from current context.

    Returns:
        Current user ID or None
    """
    return _user_id_var.get()


def set_symbol(symbol: str):
    """
    Set token symbol in current context.

    Args:
        symbol: Token symbol to set
    """
    _symbol_var.set(symbol)


def get_symbol() -> Optional[str]:
    """
    Get token symbol from current context.

    Returns:
        Current symbol or None
    """
    return _symbol_var.get()


@dataclass
class LogContext:
    """
    Context manager for structured logging with trace ID.

    Automatically:
    - Generates and sets trace ID
    - Propagates context to all log calls
    - Clears context on exit
    - Tracks timing information

    Usage:
        async with LogContext(symbol="BONK", operation="analyze", user_id=12345) as ctx:
            logger.info("Starting analysis", extra=ctx.to_dict())
            # ... do work ...
            logger.info("Analysis complete", extra=ctx.to_dict())
    """

    symbol: str = "UNKNOWN"
    operation: str = "op"
    user_id: Optional[int] = None
    extra_context: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    start_time: Optional[float] = None

    def __post_init__(self):
        """Initialize trace ID and start time."""
        if self.trace_id is None:
            self.trace_id = generate_trace_id(self.symbol, self.operation)
        self.start_time = time.time()

    async def __aenter__(self):
        """Enter async context."""
        # Set context variables
        set_trace_id(self.trace_id)
        if self.user_id:
            set_user_id(self.user_id)
        if self.symbol:
            set_symbol(self.symbol)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        # Clear context variables
        _trace_id_var.set(None)
        _user_id_var.set(None)
        _symbol_var.set(None)

    def __enter__(self):
        """Enter sync context."""
        # Set context variables
        set_trace_id(self.trace_id)
        if self.user_id:
            set_user_id(self.user_id)
        if self.symbol:
            set_symbol(self.symbol)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit sync context."""
        # Clear context variables
        _trace_id_var.set(None)
        _user_id_var.set(None)
        _symbol_var.set(None)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert context to dictionary for logging.

        Returns:
            Dictionary with all context data
        """
        context = {
            "trace_id": self.trace_id,
            "symbol": self.symbol,
            "operation": self.operation,
        }

        if self.user_id:
            context["user_id"] = self.user_id

        # Add extra context
        context.update(self.extra_context)

        return context

    def get_elapsed_ms(self) -> int:
        """
        Get elapsed time since context creation.

        Returns:
            Elapsed time in milliseconds
        """
        if self.start_time:
            return int((time.time() - self.start_time) * 1000)
        return 0

    def add_context(self, key: str, value: Any):
        """
        Add extra context data.

        Args:
            key: Context key
            value: Context value
        """
        self.extra_context[key] = value

    def get_logger_extra(self) -> Dict[str, Any]:
        """
        Get extra dict for logger calls.

        Returns:
            Dictionary ready for logger.info(..., extra=...)

        Example:
            logger.info("Message", extra=ctx.get_logger_extra())
        """
        return self.to_dict()


class ContextAwareLogger:
    """
    Logger wrapper that automatically includes context.

    Usage:
        logger = ContextAwareLogger("my.module")
        logger.info("Message")  # Automatically includes trace_id, user_id, etc.
    """

    def __init__(self, logger_name: str):
        """
        Initialize context-aware logger.

        Args:
            logger_name: Name for the logger
        """
        self.logger = logging.getLogger(logger_name)

    def _get_context_extra(self) -> Dict[str, Any]:
        """
        Get current context as extra dict.

        Returns:
            Dictionary with current context
        """
        extra = {}

        trace_id = get_trace_id()
        if trace_id:
            extra['trace_id'] = trace_id

        user_id = get_user_id()
        if user_id:
            extra['user_id'] = user_id

        symbol = get_symbol()
        if symbol:
            extra['symbol'] = symbol

        return extra

    def debug(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log debug message with context."""
        merged_extra = {**self._get_context_extra(), **(extra or {})}
        self.logger.debug(msg, extra=merged_extra, **kwargs)

    def info(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log info message with context."""
        merged_extra = {**self._get_context_extra(), **(extra or {})}
        self.logger.info(msg, extra=merged_extra, **kwargs)

    def warning(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log warning message with context."""
        merged_extra = {**self._get_context_extra(), **(extra or {})}
        self.logger.warning(msg, extra=merged_extra, **kwargs)

    def error(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log error message with context."""
        merged_extra = {**self._get_context_extra(), **(extra or {})}
        self.logger.error(msg, extra=merged_extra, **kwargs)

    def critical(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log critical message with context."""
        merged_extra = {**self._get_context_extra(), **(extra or {})}
        self.logger.critical(msg, extra=merged_extra, **kwargs)
