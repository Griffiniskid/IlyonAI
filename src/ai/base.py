"""
Base classes and types for AI provider abstraction.

This module defines the common interface for AI providers (OpenAI/OpenRouter)
and standardized request/response formats for token analysis.
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum


class AIProvider(Enum):
    """Supported AI providers"""
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    GROK = "grok"


@dataclass
class AIResponse:
    """
    Standardized response from any AI provider.

    This unified response format allows consistent handling
    of results from different AI providers.
    """

    success: bool
    provider: AIProvider
    content: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    model: str = ""
    tokens_used: int = 0
    latency_ms: int = 0
    error: Optional[str] = None

    @property
    def failed(self) -> bool:
        """Check if the request failed"""
        return not self.success


@dataclass
class TokenAnalysisRequest:
    """
    Standardized request for token analysis across all AI providers.

    This dataclass normalizes token information for consistent
    AI analysis regardless of the provider used.
    """

    # Core token identification
    address: str
    name: str
    symbol: str

    # Market data
    price_usd: float = 0
    market_cap: float = 0
    liquidity_usd: float = 0
    volume_24h: float = 0
    volume_1h: float = 0
    price_change_24h: float = 0
    price_change_1h: float = 0

    # Holder distribution
    holder_concentration: float = 0
    top_holder_pct: float = 0
    suspicious_wallets: int = 0

    # Social presence
    has_twitter: bool = False
    has_website: bool = False
    has_telegram: bool = False
    website_url: str = ""
    twitter_url: str = ""
    telegram_url: str = ""

    # On-chain security
    mint_authority_enabled: bool = False
    freeze_authority_enabled: bool = False
    liquidity_locked: bool = False
    lp_lock_percent: float = 0

    # Pool information
    age_hours: float = 0
    dex_name: str = "Unknown"

    # RugCheck data
    rugcheck_score: int = 0
    rugcheck_risks: List[str] = field(default_factory=list)

    # Website analysis
    website_content: str = ""
    website_red_flags: List[str] = field(default_factory=list)

    @classmethod
    def from_token_info(cls, token) -> "TokenAnalysisRequest":
        """
        Create TokenAnalysisRequest from TokenInfo dataclass.

        Args:
            token: TokenInfo instance

        Returns:
            TokenAnalysisRequest with all relevant fields populated
        """
        return cls(
            # Core identification
            address=token.address,
            name=token.name,
            symbol=token.symbol,

            # Market data
            price_usd=token.price_usd,
            market_cap=token.market_cap,
            liquidity_usd=token.liquidity_usd,
            volume_24h=token.volume_24h,
            volume_1h=token.volume_1h,
            price_change_24h=token.price_change_24h,
            price_change_1h=token.price_change_1h,

            # Holder distribution
            holder_concentration=token.holder_concentration,
            top_holder_pct=token.top_holder_pct,
            suspicious_wallets=token.suspicious_wallets,

            # Social presence
            has_twitter=token.has_twitter,
            has_website=token.has_website,
            has_telegram=token.has_telegram,
            website_url=token.website_url or "",
            twitter_url=token.twitter_url or "",
            telegram_url=token.telegram_url or "",

            # On-chain security
            mint_authority_enabled=token.mint_authority_enabled,
            freeze_authority_enabled=token.freeze_authority_enabled,
            liquidity_locked=token.liquidity_locked,
            lp_lock_percent=token.lp_lock_percent,

            # Pool information
            age_hours=token.age_hours,
            dex_name=token.dex_name,

            # RugCheck data
            rugcheck_score=token.rugcheck_score,
            rugcheck_risks=token.rugcheck_risks,

            # Website analysis
            website_content=token.website_content,
            website_red_flags=token.website_red_flags,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API requests"""
        return {
            "address": self.address,
            "name": self.name,
            "symbol": self.symbol,
            "price_usd": self.price_usd,
            "market_cap": self.market_cap,
            "liquidity_usd": self.liquidity_usd,
            "volume_24h": self.volume_24h,
            "volume_1h": self.volume_1h,
            "price_change_24h": self.price_change_24h,
            "price_change_1h": self.price_change_1h,
            "holder_concentration": self.holder_concentration,
            "top_holder_pct": self.top_holder_pct,
            "suspicious_wallets": self.suspicious_wallets,
            "has_twitter": self.has_twitter,
            "has_website": self.has_website,
            "has_telegram": self.has_telegram,
            "website_url": self.website_url,
            "twitter_url": self.twitter_url,
            "telegram_url": self.telegram_url,
            "mint_authority_enabled": self.mint_authority_enabled,
            "freeze_authority_enabled": self.freeze_authority_enabled,
            "liquidity_locked": self.liquidity_locked,
            "lp_lock_percent": self.lp_lock_percent,
            "age_hours": self.age_hours,
            "dex_name": self.dex_name,
            "rugcheck_score": self.rugcheck_score,
            "rugcheck_risks": self.rugcheck_risks,
            "website_content": self.website_content,
            "website_red_flags": self.website_red_flags,
        }


class BaseAIClient(ABC):
    """
    Abstract base class for all AI providers.

    All AI clients should inherit from this and implement the analyze() method.
    """

    provider: AIProvider

    @abstractmethod
    async def analyze(self, request: TokenAnalysisRequest) -> AIResponse:
        """
        Main token analysis method - must be implemented by all providers.

        Args:
            request: TokenAnalysisRequest with token information

        Returns:
            AIResponse with analysis results
        """
        pass

    async def chat(self, message: str, system_prompt: str = "") -> str:
        """
        Simple chat completion - optional override.

        Args:
            message: User message
            system_prompt: Optional system prompt

        Returns:
            AI response text

        Raises:
            NotImplementedError: If provider doesn't support chat
        """
        raise NotImplementedError(f"Chat not implemented for {self.provider.value}")

    async def close(self):
        """
        Cleanup resources - optional override.

        Should be called when shutting down the client.
        """
        pass

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """
        Helper to parse JSON from AI response text.

        Handles common formatting issues:
        - JSON in markdown code blocks
        - Extra whitespace
        - Common JSON syntax errors

        Args:
            text: Raw AI response text

        Returns:
            Parsed JSON dict, or empty dict if parsing fails
        """
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            text = json_match.group(1)

        # Clean up whitespace
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Try to extract partial JSON
            # Look for first { to last }
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass

            # If all fails, return empty dict
            return {}

    def _extract_score(self, text: str, default: int = 50) -> int:
        """
        Extract numerical score from text.

        Looks for patterns like "score: 75" or "75/100".

        Args:
            text: Text to search
            default: Default value if no score found

        Returns:
            Extracted score (0-100), or default
        """
        # Try to find "score: XX" or "score XX"
        score_match = re.search(r'score:?\s*(\d+)', text.lower())
        if score_match:
            score = int(score_match.group(1))
            return max(0, min(100, score))

        # Try to find "XX/100"
        percent_match = re.search(r'(\d+)\s*/\s*100', text)
        if percent_match:
            score = int(percent_match.group(1))
            return max(0, min(100, score))

        # Try to find standalone number
        number_match = re.search(r'\b(\d{1,3})\b', text)
        if number_match:
            score = int(number_match.group(1))
            if 0 <= score <= 100:
                return score

        return default

    def _extract_verdict(self, text: str, default: str = "CAUTION") -> str:
        """
        Extract verdict keyword from text.

        Args:
            text: Text to search
            default: Default verdict if none found

        Returns:
            One of: SAFE, CAUTION, RISKY, DANGEROUS, SCAM
        """
        text_lower = text.lower()

        verdicts = ["safe", "caution", "risky", "dangerous", "scam"]
        for verdict in verdicts:
            if verdict in text_lower:
                return verdict.upper()

        return default
