"""
Bot interaction logging adapter.

Tracks user interactions, button clicks, and bot operations.
"""

import logging
import hashlib
from typing import Dict, Any, Optional


class BotLogger:
    """Logger for bot interactions and user tracking."""

    # Exit codes for bot operations
    EXIT_SUCCESS = 20
    EXIT_TOKEN_NOT_FOUND = 21
    EXIT_ANALYSIS_FAILED = 22
    EXIT_FORMATTING_ERROR = 23
    EXIT_RATE_LIMITED = 24

    def __init__(self, logger_name: str):
        """Initialize bot logger."""
        self.logger = logging.getLogger(logger_name)

    def log_user_message(
        self,
        user_id: int,
        username: Optional[str],
        message_type: str,
        content_preview: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log incoming user message with anonymization."""
        # Anonymize username
        username_hash = None
        if username:
            username_hash = hashlib.sha256(username.encode()).hexdigest()[:12]

        self.logger.info(
            f"User message: {message_type}",
            extra={
                "user_id": user_id,
                "username_hash": username_hash,
                "message_type": message_type,
                "content_length": len(content_preview),
                "content_preview": content_preview[:100],
                **(context or {})
            }
        )

    def log_callback(
        self,
        user_id: int,
        callback_type: str,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ):
        """Log button callback."""
        self.logger.info(
            f"Callback: {callback_type}",
            extra={
                "user_id": user_id,
                "callback_type": callback_type,
                "data": data,
                **(context or {})
            }
        )

    def log_analysis_request(
        self,
        user_id: int,
        symbol: str,
        address: str,
        mode: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log analysis request."""
        self.logger.info(
            f"Analysis request: {symbol} ({mode})",
            extra={
                "user_id": user_id,
                "symbol": symbol,
                "address": address,
                "mode": mode,
                "operation": "analyze",
                **(context or {})
            }
        )

    def log_analysis_complete(
        self,
        user_id: int,
        symbol: str,
        overall_score: int,
        grade: str,
        latency_ms: int,
        exit_code: int = EXIT_SUCCESS,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log analysis completion."""
        self.logger.info(
            f"Analysis complete: {symbol} - {grade}",
            extra={
                "user_id": user_id,
                "symbol": symbol,
                "overall_score": overall_score,
                "grade": grade,
                "latency_ms": latency_ms,
                "exit_code": exit_code,
                **(context or {})
            }
        )

    def log_error(
        self,
        error: Exception,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
        exit_code: int = EXIT_ANALYSIS_FAILED
    ):
        """Log bot error."""
        self.logger.error(
            f"Bot error: {operation}",
            extra={
                "operation": operation,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "exit_code": exit_code,
                **(context or {})
            },
            exc_info=True
        )
