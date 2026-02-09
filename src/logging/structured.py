"""
Structured logging formatters for Ilyon AI.

Provides dual output formats:
- JSONFormatter: Machine-readable JSON logs for parsing and analysis
- HumanReadableFormatter: Color-coded console logs with context
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logs.

    Outputs logs as single-line JSON with structured fields for:
    - Timestamp (ISO 8601 format)
    - Log level
    - Logger name
    - Message
    - Extra context (trace_id, user_id, exit_code, etc.)
    - Exception information
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: LogRecord to format

        Returns:
            JSON string with all log data
        """
        # Build base log data
        log_data = {
            "timestamp": self.formatTime(record, datefmt='%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add trace ID if present
        if hasattr(record, 'trace_id'):
            log_data['trace_id'] = record.trace_id

        # Add user ID if present
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id

        # Add exit code if present
        if hasattr(record, 'exit_code'):
            log_data['exit_code'] = record.exit_code

        # Add symbol if present
        if hasattr(record, 'symbol'):
            log_data['symbol'] = record.symbol

        # Add operation if present
        if hasattr(record, 'operation'):
            log_data['operation'] = record.operation

        # Add AI metadata if present
        if hasattr(record, 'ai_metadata'):
            log_data['ai_metadata'] = record.ai_metadata

        # Add timing information if present
        if hasattr(record, 'timing'):
            log_data['timing'] = record.timing

        # Add latency if present
        if hasattr(record, 'latency_ms'):
            log_data['latency_ms'] = record.latency_ms

        # Add provider if present
        if hasattr(record, 'provider'):
            log_data['provider'] = record.provider

        # Add model if present
        if hasattr(record, 'model'):
            log_data['model'] = record.model

        # Add response data if present
        if hasattr(record, 'response'):
            log_data['response'] = record.response

        # Add request data if present
        if hasattr(record, 'request'):
            log_data['request'] = record.request

        # Add source if present
        if hasattr(record, 'source'):
            log_data['source'] = record.source

        # Add status_code if present
        if hasattr(record, 'status_code'):
            log_data['status_code'] = record.status_code

        # Add context if present (generic extra data)
        if hasattr(record, 'context'):
            log_data['context'] = record.context

        # Add exception information if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info)
            }

        # Convert to JSON (use default=str to handle non-serializable objects)
        try:
            return json.dumps(log_data, default=str, ensure_ascii=False)
        except Exception as e:
            # Fallback to simple JSON if formatting fails
            return json.dumps({
                "timestamp": datetime.now().isoformat(),
                "level": "ERROR",
                "logger": "logging",
                "message": f"Failed to format log: {e}",
                "original_message": str(record.msg)
            })


class HumanReadableFormatter(logging.Formatter):
    """
    Enhanced console formatter with colors and context.

    Features:
    - Color-coded log levels
    - Compact timestamp format
    - Extra context on separate lines
    - Symbol, exit code, latency indicators
    """

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m',       # Reset
        'BOLD': '\033[1m',        # Bold
        'DIM': '\033[2m',         # Dim
    }

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record for human-readable console output.

        Args:
            record: LogRecord to format

        Returns:
            Formatted string with colors and context
        """
        # Get color for log level
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        dim = self.COLORS['DIM']
        bold = self.COLORS['BOLD']

        # Format base message
        base = super().format(record)

        # Build context indicators
        context_parts = []

        # Add symbol if present
        if hasattr(record, 'symbol'):
            context_parts.append(f"Symbol: {bold}{record.symbol}{reset}{dim}")

        # Add provider and model if present
        if hasattr(record, 'provider') and hasattr(record, 'model'):
            context_parts.append(f"Provider: {record.provider} ({record.model})")
        elif hasattr(record, 'provider'):
            context_parts.append(f"Provider: {record.provider}")

        # Add exit code if present
        if hasattr(record, 'exit_code'):
            exit_code = record.exit_code
            exit_color = '\033[32m' if exit_code == 0 else '\033[31m'  # Green for 0, Red for errors
            context_parts.append(f"Exit: {exit_color}{exit_code}{reset}{dim}")

        # Add latency if present
        if hasattr(record, 'latency_ms'):
            latency = record.latency_ms
            # Color code latency (green < 1s, yellow < 3s, red >= 3s)
            if latency < 1000:
                latency_color = '\033[32m'
            elif latency < 3000:
                latency_color = '\033[33m'
            else:
                latency_color = '\033[31m'
            context_parts.append(f"Latency: {latency_color}{latency}ms{reset}{dim}")

        # Add AI token information if present
        if hasattr(record, 'ai_metadata'):
            ai_meta = record.ai_metadata
            if isinstance(ai_meta, dict):
                if 'tokens_total' in ai_meta:
                    tokens_str = f"Tokens: {ai_meta['tokens_total']}"
                    if 'tokens_prompt' in ai_meta and 'tokens_completion' in ai_meta:
                        tokens_str += f" (prompt:{ai_meta['tokens_prompt']}, completion:{ai_meta['tokens_completion']})"
                    context_parts.append(tokens_str)

                if 'cost_usd' in ai_meta:
                    cost = ai_meta['cost_usd']
                    context_parts.append(f"Cost: ${cost:.4f}")

        # Add AI response summary if present
        if hasattr(record, 'response') and isinstance(record.response, dict):
            resp = record.response
            resp_parts = []
            if 'verdict' in resp:
                resp_parts.append(f"Verdict: {resp['verdict']}")
            if 'ai_score' in resp:
                resp_parts.append(f"Score: {resp['ai_score']}/100")
            if 'confidence' in resp:
                resp_parts.append(f"Confidence: {resp['confidence']}%")
            if 'rug_probability' in resp:
                resp_parts.append(f"Rug: {resp['rug_probability']}%")

            if resp_parts:
                context_parts.append(' | '.join(resp_parts))

        # Add status code if present
        if hasattr(record, 'status_code'):
            status = record.status_code
            # Color code HTTP status (green 2xx, yellow 3xx, red 4xx/5xx)
            if 200 <= status < 300:
                status_color = '\033[32m'
            elif 300 <= status < 400:
                status_color = '\033[33m'
            else:
                status_color = '\033[31m'
            context_parts.append(f"Status: {status_color}{status}{reset}{dim}")

        # Format final output
        if context_parts:
            context_line = f"\n  {dim}→ {' | '.join(context_parts)}{reset}"
            return f"{color}{base}{reset}{context_line}"
        else:
            return f"{color}{base}{reset}"
