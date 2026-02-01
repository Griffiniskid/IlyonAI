"""
Grok (xAI) client for Twitter/Narrative analysis.

This module provides access to Grok models with live Twitter/X data access
for narrative and sentiment analysis of tokens.
"""

import json
import logging
import time
import aiohttp
import asyncio
from typing import Dict, Any, Optional, Awaitable

from src.ai.base import BaseAIClient, AIResponse, AIProvider, TokenAnalysisRequest
from src.ai.prompts.twitter import get_narrative_prompt
from src.config import settings
from src.logging.adapters.ai_logger import AILogger
from src.logging.context import generate_trace_id

logger = logging.getLogger(__name__)


class GrokClient(BaseAIClient):
    """
    Grok AI client specializing in Twitter narrative analysis.
    Uses xAI API to access live social data.
    """

    provider = AIProvider.OPENAI  # Reusing OPENAI type for now as it's a similar interface
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize Grok client.

        Args:
            api_key: Optional API key (auto-detected from settings)
            model: Model to use (defaults to settings.grok_model)
        """
        self.base_url = "https://api.x.ai/v1/chat/completions"
        self.api_key = api_key or settings.grok_api_key
        self.model = model or settings.grok_model
        
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Initialize AI logger
        self.ai_logger = AILogger("ai.grok")
        
        # Request deduplication
        self._pending_requests: Dict[str, asyncio.Task] = {}
        
        if not self.api_key:
            logger.warning("⚠️ No Grok API key configured. Narrative analysis will be skipped.")

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure we have a valid session"""
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def analyze(self, request: TokenAnalysisRequest) -> AIResponse:
        """
        Perform narrative analysis using Grok (with request deduplication).

        Args:
            request: TokenAnalysisRequest with token information

        Returns:
            AIResponse with analysis results
        """
        # Check for pending request for this token
        if request.address in self._pending_requests:
            logger.info(f"🔄 Merging duplicate Grok request for {request.symbol}")
            return await self._pending_requests[request.address]

        # Create task for the analysis
        task = asyncio.create_task(self._perform_analysis(request))
        self._pending_requests[request.address] = task
        
        try:
            return await task
        finally:
            # Cleanup
            if request.address in self._pending_requests:
                del self._pending_requests[request.address]

    async def _perform_analysis(self, request: TokenAnalysisRequest) -> AIResponse:
        """
        Internal method to execute the API call.
        """
        if not self.api_key:
            return self._create_error_response("No API key configured", time.time())
            
        start_time = time.time()
        
        # Generate trace ID
        trace_id = generate_trace_id(request.symbol, "analyze_narrative")
        context = {
            "trace_id": trace_id,
            "symbol": request.symbol,
            "address": request.address
        }

        # Build prompt using the specialized Twitter prompt generator
        # We need to recreate a minimal TokenInfo-like object or modify the prompt function
        # Since get_narrative_prompt expects TokenInfo, we'll create a temporary object
        # or just pass the request object if it has compatible fields (it mostly does)
        prompt = get_narrative_prompt(request)

        # Log request
        self.ai_logger.log_request(
            provider="grok",
            model=self.model,
            operation="analyze_narrative",
            prompt=prompt,
            params={"temperature": 0.3},
            context=context
        )

        try:
            session = await self._ensure_session()
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system", 
                        "content": "You are a crypto narrative expert with access to live Twitter/X data. usage of emojis is strictly prohibited."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "stream": False
            }

            async with session.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Grok API error: {resp.status} - {error_text}")
                    
                    self.ai_logger.log_error(
                        error=Exception(f"HTTP {resp.status}: {error_text[:100]}"),
                        provider="grok",
                        model=self.model,
                        operation="analyze_narrative",
                        context=context,
                        exit_code=AILogger.EXIT_API_ERROR
                    )
                    
                    return self._create_error_response(f"API Error: {resp.status}", start_time)

                data = await resp.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

                if not content:
                    return self._create_error_response("Empty response", start_time)

                # Parse JSON response
                result = self._parse_json_response(content)
                
                # Metrics
                usage = data.get('usage', {})
                tokens_used = usage.get('total_tokens', 0)
                tokens_prompt = usage.get('prompt_tokens', 0)
                tokens_completion = usage.get('completion_tokens', 0)
                latency_ms = int((time.time() - start_time) * 1000)

                # Log success
                self.ai_logger.log_response(
                    success=True,
                    provider="grok",
                    model=self.model,
                    operation="analyze_narrative",
                    response_data=result,
                    raw_response=content if settings.log_ai_full_responses else None,
                    tokens_used=tokens_used,
                    tokens_prompt=tokens_prompt,
                    tokens_completion=tokens_completion,
                    latency_ms=latency_ms,
                    context=context,
                    exit_code=AILogger.EXIT_SUCCESS
                )
                
                return AIResponse(
                    success=True,
                    provider=self.provider, # Using generic provider enum
                    content=result,
                    raw_text=content,
                    model=self.model,
                    tokens_used=tokens_used,
                    latency_ms=latency_ms
                )

        except Exception as e:
            logger.error(f"Grok analysis error: {e}")
            self.ai_logger.log_error(
                error=e,
                provider="grok",
                model=self.model,
                operation="analyze_narrative",
                context=context,
                exit_code=AILogger.EXIT_API_ERROR
            )
            return self._create_error_response(str(e), start_time)

    def _create_error_response(self, error: str, start_time: float) -> AIResponse:
        return AIResponse(
            success=False,
            provider=self.provider,
            content={},
            raw_text="",
            model=self.model,
            tokens_used=0,
            latency_ms=int((time.time() - start_time) * 1000),
            error=error
        )
