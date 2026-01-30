"""
AI Router for orchestrating AI analysis.

This module provides an AIRouter class that manages AI clients
for token analysis. Supports quick and full analysis modes.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.ai.base import AIResponse, TokenAnalysisRequest, AIProvider
from src.ai.openai_client import OpenAIClient
from src.core.models import TokenInfo

logger = logging.getLogger(__name__)


@dataclass
class MultiAIResult:
    """
    Results from AI analysis.

    Stores response from AI provider and aggregated metrics.
    """

    # AI response
    openai: Optional[AIResponse] = None

    # Aggregate metrics
    total_latency_ms: int = 0
    total_tokens_used: int = 0

    @property
    def success(self) -> bool:
        """Check if analysis succeeded"""
        return self.openai is not None and self.openai.success

    @property
    def any_successful(self) -> bool:
        """Check if analysis succeeded (alias for compatibility)"""
        return self.success

    @property
    def success_count(self) -> int:
        """Count how many providers succeeded (0 or 1)"""
        return 1 if self.success else 0


class AIRouter:
    """
    Routes analysis requests to appropriate AI models.

    Supports two analysis modes:
    - quick: GPT-4o-mini only (fastest, ~3-5 seconds, basic analysis)
    - standard/full: Primary model (balanced, ~10-15 seconds)

    Usage:
        router = AIRouter()
        result = await router.analyze(token, mode="standard")

        # Access results
        if result.openai and result.openai.success:
            print(result.openai.content['ai_score'])
    """

    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        """
        Initialize AI Router with AI client.

        Args:
            openai_client: Optional OpenAI client (creates default if None)
        """
        from src.config import settings

        # Determine whether to use OpenRouter (preferred) or direct OpenAI
        has_openrouter = bool(settings.openrouter_api_key)
        has_openai = bool(settings.openai_api_key)

        if has_openrouter:
            api_key_preview = settings.openrouter_api_key[:15] + "..." if len(settings.openrouter_api_key) > 15 else "***"
            logger.info(f"🔄 Using OpenRouter API for AI analysis (key: {api_key_preview})")
            # Primary client via OpenRouter
            self.openai = openai_client or OpenAIClient(use_openrouter=True)
            # Mini client via OpenRouter (GPT-4o-mini)
            self.openai_mini = OpenAIClient(model="openai/gpt-4o-mini", use_openrouter=True)
        elif has_openai:
            api_key_preview = settings.openai_api_key[:10] + "..." if len(settings.openai_api_key) > 10 else "***"
            logger.info(f"🔄 Using direct OpenAI API for AI analysis (key: {api_key_preview})")
            # Primary OpenAI client (GPT-4o)
            self.openai = openai_client or OpenAIClient()
            # Mini client for quick mode (GPT-4o-mini)
            self.openai_mini = OpenAIClient(model="gpt-4o-mini")
        else:
            logger.error("❌ No AI API key configured! Set OPENROUTER_API_KEY or OPENAI_API_KEY in .env")
            # Create clients anyway (they will fail but with clear error)
            self.openai = openai_client or OpenAIClient()
            self.openai_mini = OpenAIClient(model="gpt-4o-mini")

        logger.info("✅ AI Router initialized")

    async def analyze(
        self,
        token: TokenInfo,
        mode: str = "standard"
    ) -> MultiAIResult:
        """
        Run AI analysis based on mode.

        Args:
            token: TokenInfo with all token data
            mode: Analysis mode ("quick", "standard", or "full")

        Returns:
            MultiAIResult with AI response

        Modes:
            - "quick": GPT-4o-mini only (~3-5 seconds)
              * Fastest option
              * Basic technical analysis
              * Good for quick checks

            - "standard" / "full": Primary model (~10-15 seconds)
              * Comprehensive technical analysis
              * Default mode
        """
        request = TokenAnalysisRequest.from_token_info(token)
        result = MultiAIResult()
        start_time = time.time()

        logger.info(f"🤖 Starting {mode} analysis for {token.symbol}")

        try:
            if mode == "quick":
                result = await self._quick_analysis(request)
            else:
                # Both "standard" and "full" use primary model
                result = await self._standard_analysis(request)

        except Exception as e:
            logger.error(f"Analysis error in mode {mode}: {e}", exc_info=True)

        # Calculate total metrics
        result.total_latency_ms = int((time.time() - start_time) * 1000)
        result.total_tokens_used = result.openai.tokens_used if result.openai and result.openai.success else 0

        logger.info(
            f"✅ {mode.upper()} analysis complete for {token.symbol}: "
            f"{'success' if result.success else 'failed'}, "
            f"{result.total_latency_ms}ms, "
            f"{result.total_tokens_used} tokens"
        )

        return result

    async def _quick_analysis(self, request: TokenAnalysisRequest) -> MultiAIResult:
        """
        Quick analysis using GPT-4o-mini only.

        Fast and cost-effective for basic token checks.
        """
        result = MultiAIResult()

        try:
            result.openai = await self.openai_mini.analyze(request)
            logger.info("✅ Quick analysis (GPT-4o-mini) complete")
        except Exception as e:
            logger.error(f"Quick analysis error: {e}")

        return result

    async def _standard_analysis(self, request: TokenAnalysisRequest) -> MultiAIResult:
        """
        Standard analysis using primary model.

        Balanced approach with comprehensive technical analysis.
        """
        result = MultiAIResult()

        try:
            result.openai = await self.openai.analyze(request)
            logger.info("✅ Standard analysis complete")
        except Exception as e:
            logger.error(f"Standard analysis error: {e}")

        return result

    async def chat(self, message: str, system_prompt: str = "") -> str:
        """
        Simple chat using GPT-4o-mini for cost efficiency.

        Args:
            message: User message
            system_prompt: Optional system prompt

        Returns:
            AI response text
        """
        return await self.openai_mini.chat(message, system_prompt)

    async def close(self):
        """Cleanup all AI clients"""
        logger.info("🔄 Closing AI Router...")

        try:
            await self.openai.close()
            await self.openai_mini.close()
            logger.info("✅ AI clients closed")

        except Exception as e:
            logger.error(f"Error closing AI clients: {e}")
