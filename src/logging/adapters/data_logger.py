"""
Data source API logging adapter.

Tracks external API calls, retries, and data extraction.
"""

import logging
from typing import Dict, Any, Optional


class DataLogger:
    """Logger for data source API operations."""

    # Exit codes for data operations
    EXIT_SUCCESS = 10
    EXIT_TIMEOUT = 11
    EXIT_HTTP_ERROR = 12
    EXIT_PARSE_ERROR = 13
    EXIT_RATE_LIMITED = 14
    EXIT_NOT_FOUND = 15

    def __init__(self, logger_name: str):
        """Initialize data logger."""
        self.logger = logging.getLogger(logger_name)

    def log_api_call(
        self,
        source: str,
        endpoint: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ):
        """Log data source API call."""
        self.logger.info(
            f"{source} API call",
            extra={
                "source": source,
                "endpoint": endpoint,
                "params": params,
                "operation": "api_call",
                **(context or {})
            }
        )

    def log_api_response(
        self,
        source: str,
        success: bool,
        status_code: int,
        has_data: bool,
        latency_ms: int,
        exit_code: int,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log API response."""
        log_level = logging.INFO if success else logging.WARNING

        self.logger.log(
            log_level,
            f"{source} API response: {status_code}",
            extra={
                "source": source,
                "success": success,
                "status_code": status_code,
                "has_data": has_data,
                "latency_ms": latency_ms,
                "exit_code": exit_code,
                **(context or {})
            }
        )

    def log_retry(
        self,
        source: str,
        attempt: int,
        max_retries: int,
        reason: str,
        delay_ms: int,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log retry attempt."""
        self.logger.warning(
            f"{source} retry {attempt}/{max_retries}: {reason}",
            extra={
                "source": source,
                "retry_attempt": attempt,
                "max_retries": max_retries,
                "reason": reason,
                "delay_ms": delay_ms,
                **(context or {})
            }
        )

    def log_data_extraction(
        self,
        source: str,
        data_type: str,
        extracted: bool,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log data extraction result."""
        self.logger.debug(
            f"{source} extracted {data_type}: {extracted}",
            extra={
                "source": source,
                "data_type": data_type,
                "extracted": extracted,
                **(context or {})
            }
        )

    def log_error(
        self,
        error: Exception,
        source: str,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
        exit_code: int = EXIT_HTTP_ERROR
    ):
        """Log data source error."""
        self.logger.error(
            f"{source} error: {operation}",
            extra={
                "source": source,
                "operation": operation,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "exit_code": exit_code,
                **(context or {})
            },
            exc_info=True
        )
