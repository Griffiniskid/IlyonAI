"""
Performance tracking logging adapter.

Tracks timing, stage execution, and performance metrics.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional


class PerformanceLogger:
    """Logger for performance tracking and timing."""

    # Exit codes for performance operations
    EXIT_SUCCESS = 30
    EXIT_DATA_COLLECTION_FAILED = 31
    EXIT_AI_ANALYSIS_FAILED = 32
    EXIT_SCORING_FAILED = 33
    EXIT_CACHE_ERROR = 34

    def __init__(self, logger_name: str):
        """Initialize performance logger."""
        self.logger = logging.getLogger(logger_name)

    def log_stage_start(
        self,
        stage: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log pipeline stage start."""
        self.logger.debug(
            f"Stage start: {stage}",
            extra={
                "stage": stage,
                "event": "stage_start",
                **(context or {})
            }
        )

    def log_stage_complete(
        self,
        stage: str,
        duration_ms: int,
        success: bool,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log pipeline stage completion."""
        log_level = logging.INFO if success else logging.WARNING

        self.logger.log(
            log_level,
            f"Stage complete: {stage} ({duration_ms}ms)",
            extra={
                "stage": stage,
                "duration_ms": duration_ms,
                "success": success,
                "event": "stage_complete",
                **(context or {})
            }
        )

    def log_cache_operation(
        self,
        operation: str,
        hit: bool,
        key: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log cache operation."""
        self.logger.debug(
            f"Cache {operation}: {'HIT' if hit else 'MISS'} ({key})",
            extra={
                "operation": operation,
                "cache_hit": hit,
                "cache_key": key,
                **(context or {})
            }
        )

    @asynccontextmanager
    async def timed(self, operation: str, context: Optional[Dict[str, Any]] = None):
        """Context manager for timing operations."""
        start_time = time.time()
        success = True
        try:
            self.log_stage_start(operation, context)
            yield
        except Exception:
            success = False
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            self.log_stage_complete(operation, duration_ms, success, context)

    def log_timing(
        self,
        operation: str,
        duration_ms: int,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log operation timing."""
        self.logger.info(
            f"Timing: {operation} - {duration_ms}ms",
            extra={
                "operation": operation,
                "timing": {"operation": operation, "duration_ms": duration_ms},
                **(context or {})
            }
        )
