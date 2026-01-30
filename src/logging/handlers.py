"""
Custom logging handlers for AI Sentinel.

Provides specialized file handlers with:
- Automatic directory creation
- Rotating file management
- JSON and text format support
"""

import logging.handlers
from pathlib import Path
from typing import Optional


class StructuredFileHandler(logging.handlers.RotatingFileHandler):
    """
    Rotating file handler with automatic directory creation.

    Features:
    - Creates parent directories if they don't exist
    - Rotates logs when max size is reached
    - Maintains backup count
    - UTF-8 encoding by default
    """

    def __init__(
        self,
        filename: str,
        mode: str = 'a',
        maxBytes: int = 10 * 1024 * 1024,  # 10MB default
        backupCount: int = 5,
        encoding: Optional[str] = 'utf-8',
        delay: bool = False
    ):
        """
        Initialize structured file handler.

        Args:
            filename: Log file path
            mode: File open mode (default: 'a' for append)
            maxBytes: Maximum file size before rotation (default: 10MB)
            backupCount: Number of backup files to keep (default: 5)
            encoding: File encoding (default: 'utf-8')
            delay: Delay file opening until first emit (default: False)
        """
        # Ensure parent directory exists
        log_path = Path(filename)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize parent class
        super().__init__(
            filename=filename,
            mode=mode,
            maxBytes=maxBytes,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay
        )

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        """
        Determine if rollover should occur.

        Args:
            record: Log record to check

        Returns:
            True if file should be rotated
        """
        # Use parent class logic
        return super().shouldRollover(record)

    def doRollover(self):
        """
        Perform a rollover (create new log file, archive old one).
        """
        super().doRollover()


class ComponentFileHandler(StructuredFileHandler):
    """
    File handler for component-specific logs.

    Creates separate log files for different components (AI, bot, data, etc.).
    Useful for isolating logs by subsystem.
    """

    def __init__(
        self,
        component: str,
        log_dir: str = "logs",
        maxBytes: int = 10 * 1024 * 1024,
        backupCount: int = 5
    ):
        """
        Initialize component file handler.

        Args:
            component: Component name (e.g., 'ai', 'bot', 'data')
            log_dir: Directory for log files (default: 'logs')
            maxBytes: Maximum file size before rotation (default: 10MB)
            backupCount: Number of backup files to keep (default: 5)
        """
        # Build filename
        filename = f"{log_dir}/{component}.json"

        # Initialize parent
        super().__init__(
            filename=filename,
            maxBytes=maxBytes,
            backupCount=backupCount
        )

        self.component = component

    def emit(self, record: logging.LogRecord):
        """
        Emit a log record.

        Only emits if the logger name starts with the component name.

        Args:
            record: Log record to emit
        """
        # Filter by component
        if record.name.startswith(self.component):
            super().emit(record)
