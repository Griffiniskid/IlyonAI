"""
AI operation logging adapter.

Provides comprehensive logging for AI provider operations including:
- Request logging with prompts and parameters
- Response logging with tokens, latency, and costs
- Error logging with exit codes
- Cost calculation per model
"""

import logging
import time
from typing import Dict, Any, Optional
from src.logging.context import get_trace_id, get_symbol


class AILogger:
    """
    Specialized logger for AI operations.

    Features:
    - Full request/response logging
    - Token usage and cost tracking
    - Exit code standardization
    - Provider-specific metadata
    - Automatic trace ID propagation
    """

    # Exit codes for AI operations
    EXIT_SUCCESS = 0
    EXIT_TIMEOUT = 1
    EXIT_API_ERROR = 2
    EXIT_PARSE_ERROR = 3
    EXIT_EMPTY_RESPONSE = 4
    EXIT_RATE_LIMITED = 5

    # Pricing per 1M tokens (input/output) in USD
    # Updated as of December 2025
    PRICING = {
        # OpenRouter
        "deepseek/deepseek-v3.2-exp": {"input": 0.27, "output": 1.10},
        "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},

        # Google Gemini
        "gemini-2.0-flash-exp": {"input": 0.075, "output": 0.30},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},

        # xAI Grok
        "grok-2-latest": {"input": 2.00, "output": 10.00},
        "grok-beta": {"input": 5.00, "output": 15.00},
        "grok-4.1-fast": {"input": 0.50, "output": 2.00},
    }

    def __init__(self, logger_name: str):
        """
        Initialize AI logger.

        Args:
            logger_name: Logger name (e.g., 'ai.openai', 'ai.gemini')
        """
        self.logger = logging.getLogger(logger_name)

    def log_request(
        self,
        provider: str,
        model: str,
        operation: str,
        prompt: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Log AI request.

        Args:
            provider: AI provider name (openai, gemini, grok)
            model: Model name
            operation: Operation type (analyze, chat, etc.)
            prompt: Prompt text
            params: Request parameters (temperature, max_tokens, etc.)
            context: Additional context
        """
        # Get trace ID from context if not provided
        trace_id = (context or {}).get('trace_id') or get_trace_id()
        symbol = (context or {}).get('symbol') or get_symbol()

        # Truncate prompt for preview
        prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt

        self.logger.info(
            f"AI request: {operation}",
            extra={
                "trace_id": trace_id,
                "provider": provider,
                "model": model,
                "operation": operation,
                "symbol": symbol,
                "prompt_length": len(prompt),
                "prompt_preview": prompt_preview,
                "request": {
                    "params": params,
                    "prompt_chars": len(prompt)
                },
                **(context or {})
            }
        )

    def log_response(
        self,
        success: bool,
        provider: str,
        model: str,
        operation: str,
        response_data: Dict[str, Any],
        raw_response: Optional[str],
        tokens_used: int,
        latency_ms: int,
        context: Optional[Dict[str, Any]] = None,
        exit_code: int = 0,
        tokens_prompt: int = 0,
        tokens_completion: int = 0
    ):
        """
        Log AI response with full metadata.

        Args:
            success: Whether the request succeeded
            provider: AI provider name
            model: Model name
            operation: Operation type
            response_data: Parsed response data
            raw_response: Raw response text (optional)
            tokens_used: Total tokens used
            latency_ms: Request latency in milliseconds
            context: Additional context
            exit_code: Exit code (0=success, >0=error)
            tokens_prompt: Prompt tokens (if available)
            tokens_completion: Completion tokens (if available)
        """
        # Get trace ID from context if not provided
        trace_id = (context or {}).get('trace_id') or get_trace_id()
        symbol = (context or {}).get('symbol') or get_symbol()

        # Calculate cost
        cost_usd = self._calculate_cost(
            model=model,
            tokens_prompt=tokens_prompt or (tokens_used // 2),
            tokens_completion=tokens_completion or (tokens_used // 2)
        )

        # Prepare raw response preview
        raw_preview = None
        if raw_response:
            raw_preview = raw_response[:200] if len(raw_response) > 200 else raw_response

        # Build AI metadata
        ai_metadata = {
            "provider": provider,
            "model": model,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "tokens_total": tokens_used,
            "latency_ms": latency_ms,
            "cost_usd": round(cost_usd, 6)
        }

        # Log level based on success
        log_level = logging.INFO if success else logging.WARNING

        self.logger.log(
            log_level,
            f"AI response: {'success' if success else 'failed'}",
            extra={
                "trace_id": trace_id,
                "provider": provider,
                "model": model,
                "operation": operation,
                "symbol": symbol,
                "exit_code": exit_code,
                "latency_ms": latency_ms,
                "ai_metadata": ai_metadata,
                "response": response_data,
                "raw_response_preview": raw_preview,
                **(context or {})
            }
        )

    def log_error(
        self,
        error: Exception,
        provider: str,
        model: str,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
        exit_code: int = EXIT_API_ERROR
    ):
        """
        Log AI error.

        Args:
            error: Exception that occurred
            provider: AI provider name
            model: Model name
            operation: Operation type
            context: Additional context
            exit_code: Error exit code
        """
        # Get trace ID from context if not provided
        trace_id = (context or {}).get('trace_id') or get_trace_id()
        symbol = (context or {}).get('symbol') or get_symbol()

        self.logger.error(
            f"AI error: {operation} - {type(error).__name__}",
            extra={
                "trace_id": trace_id,
                "provider": provider,
                "model": model,
                "operation": operation,
                "symbol": symbol,
                "exit_code": exit_code,
                "error_type": type(error).__name__,
                "error_message": str(error),
                **(context or {})
            },
            exc_info=True
        )

    def log_synthesis(
        self,
        providers_used: list,
        synthesis_successful: bool,
        latency_ms: int,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Log multi-provider synthesis operation.

        Args:
            providers_used: List of providers that succeeded
            synthesis_successful: Whether synthesis succeeded
            latency_ms: Synthesis latency
            context: Additional context
        """
        trace_id = (context or {}).get('trace_id') or get_trace_id()
        symbol = (context or {}).get('symbol') or get_symbol()

        self.logger.info(
            f"Multi-LLM synthesis: {'success' if synthesis_successful else 'failed'}",
            extra={
                "trace_id": trace_id,
                "symbol": symbol,
                "operation": "synthesis",
                "providers_count": len(providers_used),
                "providers": providers_used,
                "success": synthesis_successful,
                "latency_ms": latency_ms,
                "exit_code": self.EXIT_SUCCESS if synthesis_successful else self.EXIT_API_ERROR,
                **(context or {})
            }
        )

    def _calculate_cost(self, model: str, tokens_prompt: int, tokens_completion: int) -> float:
        """
        Calculate AI API cost based on token usage.

        Args:
            model: Model name
            tokens_prompt: Number of prompt tokens
            tokens_completion: Number of completion tokens

        Returns:
            Cost in USD
        """
        # Get pricing for model (default to DeepSeek if not found)
        pricing = self.PRICING.get(model, self.PRICING.get("deepseek/deepseek-v3.2-exp", {"input": 0.27, "output": 1.10}))

        # Calculate cost (pricing is per 1M tokens)
        input_cost = (tokens_prompt / 1_000_000) * pricing["input"]
        output_cost = (tokens_completion / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    @staticmethod
    def get_exit_code_name(exit_code: int) -> str:
        """
        Get human-readable name for exit code.

        Args:
            exit_code: Exit code number

        Returns:
            Exit code name
        """
        exit_code_names = {
            0: "SUCCESS",
            1: "TIMEOUT",
            2: "API_ERROR",
            3: "PARSE_ERROR",
            4: "EMPTY_RESPONSE",
            5: "RATE_LIMITED"
        }
        return exit_code_names.get(exit_code, f"UNKNOWN_{exit_code}")
