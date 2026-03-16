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
from src.ai.grok_client import GrokClient
from src.core.models import TokenInfo
from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MultiAIResult:
    """
    Results from AI analysis.

    Stores response from AI provider and aggregated metrics.
    """

    # AI responses
    openai: Optional[AIResponse] = None
    grok: Optional[AIResponse] = None  # New field for Grok results

    # Aggregate metrics
    total_latency_ms: int = 0
    total_tokens_used: int = 0

    @property
    def success(self) -> bool:
        """Check if analysis succeeded"""
        # Primarily check standard analysis, but also valid if just Grok works in some contexts
        return (self.openai is not None and self.openai.success) or \
               (self.grok is not None and self.grok.success)

    @property
    def any_successful(self) -> bool:
        """Check if analysis succeeded (alias for compatibility)"""
        return self.success

    @property
    def success_count(self) -> int:
        """Count how many providers succeeded"""
        count = 0
        if self.openai and self.openai.success: count += 1
        if self.grok and self.grok.success: count += 1
        return count


class AIRouter:
    """
    Routes analysis requests to appropriate AI models.

    Supports two analysis modes:
    - quick: DeepSeek via OpenRouter only
    - standard/full: DeepSeek + Grok (parallel execution)

    Usage:
        router = AIRouter()
        result = await router.analyze(token, mode="standard")
    """

    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        """
        Initialize AI Router with AI clients.

        Args:
            openai_client: Optional OpenAI client (creates default if None)
        """
        # OpenRouter is required for all non-Grok AI analysis.
        has_openrouter = bool(settings.openrouter_api_key)

        if has_openrouter:
            api_key_preview = settings.openrouter_api_key[:15] + "..." if len(settings.openrouter_api_key) > 15 else "***"
            logger.info(f"🔄 Using OpenRouter API for AI analysis (key: {api_key_preview})")
            self.openai = openai_client or OpenAIClient(model=settings.ai_model, use_openrouter=True)
            self.openai_mini = OpenAIClient(model=settings.ai_model, use_openrouter=True)
        else:
            logger.error("❌ No OpenRouter API key configured! Set OPENROUTER_API_KEY in .env for DeepSeek analysis")
            self.openai = None
            self.openai_mini = None
            
        # Initialize Grok client
        if settings.grok_api_key:
            logger.info(f"🔄 Initializing Grok client for narrative analysis ({settings.grok_model})")
            self.grok = GrokClient()
        else:
            logger.info("⚠️ Grok API key missing - narrative analysis disabled")
            self.grok = None

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
        """
        request = TokenAnalysisRequest.from_token_info(token)
        result = MultiAIResult()
        start_time = time.time()

        logger.info(f"🤖 Starting {mode} analysis for {token.symbol}")

        try:
            if mode == "quick":
                # Quick mode: Only technical analysis with mini model
                result = await self._quick_analysis(request)
            else:
                # Standard/Full mode: Parallel execution of Technical + Narrative
                # Both "standard" and "full" use primary model + Grok
                result = await self._standard_analysis(request)

        except Exception as e:
            logger.error(f"Analysis error in mode {mode}: {e}", exc_info=True)

        # Calculate total metrics
        result.total_latency_ms = int((time.time() - start_time) * 1000)
        
        # Sum tokens used
        openai_tokens = result.openai.tokens_used if result.openai and result.openai.success else 0
        grok_tokens = result.grok.tokens_used if result.grok and result.grok.success else 0
        result.total_tokens_used = openai_tokens + grok_tokens

        logger.info(
            f"✅ {mode.upper()} analysis complete for {token.symbol}: "
            f"{'success' if result.success else 'failed'}, "
            f"{result.total_latency_ms}ms, "
            f"{result.total_tokens_used} tokens"
        )

        return result

    async def _quick_analysis(self, request: TokenAnalysisRequest) -> MultiAIResult:
        """
        Quick analysis using DeepSeek via OpenRouter.
        """
        result = MultiAIResult()

        try:
            if not self.openai_mini:
                return result
            result.openai = await self.openai_mini.analyze(request)
            logger.info(f"✅ Quick analysis ({settings.ai_model}) complete")
        except Exception as e:
            logger.error(f"Quick analysis error: {e}")

        return result

    async def _standard_analysis(self, request: TokenAnalysisRequest) -> MultiAIResult:
        """
        Standard analysis using primary model AND Grok in parallel.
        """
        result = MultiAIResult()

        if not self.openai:
            return result

        # Define tasks to run in parallel
        tasks = [self.openai.analyze(request)]
        
        # Add Grok task if client is available
        if self.grok:
            tasks.append(self.grok.analyze(request))
        else:
            # Placeholder for consistent unpacking if needed, 
            # but simpler to just handle variable length results or check indices
            pass

        try:
            # Run concurrently
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process OpenAI result (always first)
            openai_resp = responses[0]
            if isinstance(openai_resp, Exception):
                logger.error(f"OpenAI analysis failed: {openai_resp}")
            else:
                result.openai = openai_resp
                logger.info(f"✅ DeepSeek technical analysis complete ({settings.ai_model})")

            # Process Grok result (if it ran)
            if self.grok and len(responses) > 1:
                grok_resp = responses[1]
                if isinstance(grok_resp, Exception):
                    logger.error(f"Grok analysis failed: {grok_resp}")
                else:
                    result.grok = grok_resp
                    logger.info("✅ Grok narrative analysis complete")
                    
        except Exception as e:
            logger.error(f"Standard analysis error: {e}")

        return result

    async def chat(self, message: str, system_prompt: str = "") -> str:
        """
        Simple chat using DeepSeek via OpenRouter.
        """
        if not self.openai_mini:
            return ""
        return await self.openai_mini.chat(message, system_prompt)

    async def close(self):
        """Cleanup all AI clients"""
        logger.info("🔄 Closing AI Router...")

        try:
            if self.openai:
                await self.openai.close()
            if self.openai_mini:
                await self.openai_mini.close()
            if self.grok:
                await self.grok.close()
            logger.info("✅ AI clients closed")

        except Exception as e:
            logger.error(f"Error closing AI clients: {e}")
