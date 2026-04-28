"""
OpenAI/OpenRouter AI client for token analysis.

This module provides GPT-powered token analysis with comprehensive
smart contract auditing, whale analysis, and risk assessment.
"""

import json
import re
import logging
import time
import asyncio
from typing import Dict, Any, Optional
import aiohttp

from .base import BaseAIClient, AIResponse, AIProvider, TokenAnalysisRequest
from ..config import settings
from ..logging.adapters.ai_logger import AILogger
from ..logging.context import generate_trace_id

logger = logging.getLogger(__name__)


class OpenAIClient(BaseAIClient):
    """
    GPT-powered analysis engine for comprehensive token evaluation.

    Supports both direct OpenAI API and OpenRouter gateway for multi-model access.
    """

    provider = AIProvider.OPENAI

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        use_openrouter: bool = False
    ):
        """
        Initialize OpenAI client.

        Args:
            api_key: Optional API key (auto-detected from settings if None)
            model: Model to use (auto-detected from settings if None)
            use_openrouter: Use OpenRouter instead of direct OpenAI API
        """
        self.use_openrouter = use_openrouter

        if use_openrouter:
            self.provider = AIProvider.OPENROUTER
            self.base_url = "https://openrouter.ai/api/v1/chat/completions"
            self.api_key = api_key or settings.openrouter_api_key
            self.model = model or settings.ai_model
        else:
            self.base_url = "https://api.openai.com/v1/chat/completions"
            self.api_key = api_key or settings.openai_api_key
            self.model = model or settings.openai_model

        self._session: Optional[aiohttp.ClientSession] = None

        # Initialize AI logger
        self.ai_logger = AILogger(f"ai.{self.provider.value}")

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

    def _get_system_prompt(self) -> str:
        """
        System prompt for the AI analyst.

        Defines the AI's role, expertise, and response requirements.
        """
        return """You are an ELITE cryptocurrency analyst specializing in:
- Smart contract auditing (Solidity, Rust, security patterns)
- Tokenomics and whale analysis
- On-chain analysis and scam detection
- Market sentiment and social signals

Your PRIMARY GOAL is to PROTECT users from financial loss.
Be STRICT but CONTEXT-AWARE.
- MEMECOINS: Judge based on "vibe", community strength, and originality. Do NOT penalize for lack of whitepaper/utility if the meme culture is strong.
- UTILITY/DEFI: Judge based on roadmap, team transparency, and technical depth. Penalize heavily for vagueness.
- SCAMS: Penalize hard for broken websites, honeypot code, or fake teams.

Use the FULL 0-100 range.
- 90-100: Exceptional quality (rare)
- 70-89: Solid, safe projects
- 40-69: Average/Risky
- 0-39: Dangerous/Scam

Respond ONLY with valid JSON without markdown formatting."""

    def _format_website_content_section(self, request: TokenAnalysisRequest) -> str:
        """
        Format website content section for AI analysis.

        Includes actual website content when available for AI to analyze
        for professionalism, scam patterns, and legitimacy.

        Args:
            request: TokenAnalysisRequest with website data

        Returns:
            Formatted website content section string
        """
        if not request.has_website:
            return ""

        website_content = request.website_content.strip() if request.website_content else ""

        if not website_content or len(website_content) < 50:
            return "\n- Content: Unable to retrieve website content"

        # Truncate to reasonable size for AI context (max 4000 chars)
        if len(website_content) > 4000:
            website_content = website_content[:4000] + "...(truncated)"

        return f"""

---BEGIN WEBSITE CONTENT---
{website_content}
---END WEBSITE CONTENT---

WEBSITE CONTENT ANALYSIS INSTRUCTIONS:
Analyze the website content above for:
1. Professional language vs hype/scam patterns ("buy now!", "guaranteed returns")
2. Specific technical details vs vague promises
3. Team information quality (real names/backgrounds vs anonymous)
4. Tokenomics clarity (specific numbers vs buzzwords)
5. Grammar and spelling quality
6. Urgency language ("limited time!", "don't miss out!")
7. Unrealistic promises ("1000x", "to the moon", "guaranteed profit")
8. Copy-paste template content (lorem ipsum, placeholder text)
9. Crypto scam patterns (Elon Musk mentions, "anti-whale", etc.)"""

    def _format_liquidity_lock_text(self, request: TokenAnalysisRequest) -> str:
        if request.liquidity_locked is True:
            if request.lp_lock_percent is not None and request.lp_lock_percent > 0:
                return f"LOCKED ({request.lp_lock_percent:.1f}%)"
            return "LOCKED (verified, percentage unavailable)"
        if request.liquidity_locked is False:
            return "NOT LOCKED - verified rug risk"
        note = request.liquidity_lock_note or "lock status not verified"
        return f"UNKNOWN - {note}"

    def _format_rug_pull_risk(self, request: TokenAnalysisRequest) -> str:
        if request.liquidity_locked is False and request.mint_authority_enabled:
            return "CRITICAL"
        if request.liquidity_locked is False or request.mint_authority_enabled:
            return "HIGH"
        if request.liquidity_locked is None:
            return "UNKNOWN - LP lock could not be verified, do not assume locked or unlocked"
        return "Low"

    def _build_analysis_prompt(self, request: TokenAnalysisRequest) -> str:
        """
        Build comprehensive analysis prompt from token data.

        Args:
            request: TokenAnalysisRequest with all token information

        Returns:
            Formatted prompt string with complete technical analysis
        """
        # Calculate derived metrics
        volume_liq_ratio = (request.volume_24h / request.liquidity_usd * 100) if request.liquidity_usd > 0 else 0

        # Determine trend
        if request.price_change_24h > 10:
            trend = "UPTREND"
        elif request.price_change_24h < -10:
            trend = "DOWNTREND"
        else:
            trend = "SIDEWAYS"

        # Build comprehensive technical data
        liquidity_lock_text = self._format_liquidity_lock_text(request)
        rug_pull_risk = self._format_rug_pull_risk(request)

        prompt = f"""
==========================================================
COMPREHENSIVE TOKEN ANALYSIS
==========================================================

BASIC INFORMATION:
- Name: {request.name}
- Symbol: ${request.symbol}
- Address: {request.address}
- Age: {request.age_hours:.1f} hours ({request.age_hours/24:.1f} days)
- DEX: {request.dex_name}

MARKET DATA:
- Price: ${request.price_usd:.10f}
- Market Cap: ${request.market_cap:,.0f}
- Liquidity: ${request.liquidity_usd:,.0f}
- Volume 24h: ${request.volume_24h:,.0f}
- Volume/Liquidity Ratio: {volume_liq_ratio:.1f}%

PRICE MOMENTUM:
- 1 hour: {request.price_change_1h:+.2f}%
- 24 hours: {request.price_change_24h:+.2f}%
- Trend: {trend}

CONTRACT SECURITY (CRITICAL):
- Mint Authority: {"ENABLED - dev can create new tokens!" if request.mint_authority_enabled else "DISABLED - supply is fixed"}
- Freeze Authority: {"ENABLED - dev can freeze wallets!" if request.freeze_authority_enabled else "DISABLED - no freeze risk"}
- LP Lock: {liquidity_lock_text}
- RugCheck Score: {request.rugcheck_score} (0=excellent, >1000=dangerous)
- RugCheck Risks: {', '.join(request.rugcheck_risks) if request.rugcheck_risks else 'None detected'}

HOLDER ANALYSIS:
- Top 10 Concentration: {request.holder_concentration:.1f}%
- Top 1 Wallet: {request.top_holder_pct:.1f}%
- Suspicious Wallets: {request.suspicious_wallets}

SOCIAL PRESENCE:
- Twitter: {"YES" if request.has_twitter else "NO - red flag!"}
- Website: {"YES" if request.has_website else "NO - suspicious"}
- Telegram: {"YES" if request.has_telegram else "NO"}
- Social Score: {sum([request.has_twitter, request.has_website, request.has_telegram])}/3

RISK PATTERN DETECTION:
- New Token (<24h): {"YES - high risk!" if request.age_hours < 24 else "No"}
- Micro-cap (<$50K): {"YES - easily manipulated" if request.market_cap < 50000 else "No"}
- Low Liquidity (<$10K): {"YES - impossible to exit!" if request.liquidity_usd < 10000 else "No"}
- Pump & Dump Signal: {"LIKELY" if request.price_change_24h < -50 and request.age_hours < 72 else "Possible" if request.price_change_24h < -30 else "Not detected"}
- Rug Pull Risk: {rug_pull_risk}

WEBSITE ANALYSIS:
- URL: {request.website_url if request.has_website else "NO WEBSITE"}
- Red Flags: {', '.join(request.website_red_flags) if request.website_red_flags else 'None'}
{self._format_website_content_section(request)}

==========================================================
ANALYSIS REQUIREMENTS
==========================================================

Analyze ALL data above and provide EXPERT assessment:

1. **CODE AUDIT**: Evaluate contract security (Mint/Freeze/LP Lock)
2. **WHALE ANALYSIS**: Evaluate distribution and manipulation risk
3. **SENTIMENT**: Evaluate social presence and trust signals
4. **TRADING PATTERNS**: Evaluate activity patterns and anomalies
5. **RUG PROBABILITY**: Estimate scam likelihood (0-100%)

==========================================================
SCORING CALIBRATION RULES (CRITICAL - FOLLOW EXACTLY)
==========================================================

IMPORTANT: Your score contributes 40% to the final weighted grade.
The other 60% comes from objective metrics (liquidity, locks, etc.).
Your job is to judge the QUALITATIVE aspects: Code quality, Website professionalism, Sentiment, and Narrative.

First, IDENTIFY THE TOKEN TYPE:
- MEMECOIN: No utility, community-focused, humor-based.
- UTILITY/DEFI: Promises product, yield, or tech.
- SCAM: Obvious copy-paste, honeypot, fake promises.

SCORE 80-100 (SAFE / STRONG):
- Mint Authority DISABLED ✓
- Freeze Authority DISABLED ✓
- LP Lock 95%+ with verified duration ✓
- At least 2 social channels (Twitter + Website or Telegram) ✓
- Holder concentration <40% ✓
- No suspicious trading patterns ✓
- MEME: Funny/original website, active community, "good vibes".
- UTILITY: Doxxed team, clear whitepaper, working product.

SCORE 60-79 (CAUTION / AVERAGE):
- Good security fundamentals (no mint auth, LP locked)
- Partial social presence (1-2 channels)
- Moderate holder concentration (40-60%)
- MEME: Generic but functional website, standard template but clean.
- UTILITY: Anon team but good code, roadmap exists but vague.

SCORE 40-59 (RISKY):
- Security concerns (freeze authority enabled, low LP lock%)
- Missing key socials (no Twitter OR no Website)
- High holder concentration (60-80%)
- Suspicious data anomalies
- MEME: Low effort, "lorem ipsum" texts, broken links.
- UTILITY: No whitepaper, no product, broken promises.

SCORE 20-39 (DANGEROUS):
- Mint Authority ENABLED = strong reason to score low
- LP NOT LOCKED = strong reason to score low
- NO social presence at all
- Very high holder concentration (>80%)
- Clear manipulation patterns

SCORE 0-19 (SCAM):
- Multiple CRITICAL red flags simultaneously
- Evidence of active rug patterns
- Honeypot characteristics detected
- Fake or stolen socials
- Already dumping/rugged

RED FLAG SEVERITY LEVELS:
- CRITICAL: Mint Authority ON, LP Unlocked, Zero Socials, Known Scammer
- HIGH: Freeze ON, Low LP lock%, Very high concentration (>80%)
- MEDIUM: Missing some socials, Moderate concentration, Suspicious data quality
- LOW: Minor concerns, needs monitoring

GREEN FLAG CONFIDENCE LEVELS:
- HIGH: Mint/Freeze disabled, LP locked, all socials present, healthy distribution
- MEDIUM: Good security but limited social presence, or vice versa
- LOW: Some positive signals but insufficient data to confirm

Respond STRICTLY in JSON format:
{{
    "ai_score": <0-100 safety score following calibration rules above>,
    "ai_confidence": <0-100 confidence in your analysis>,
    "ai_rug_probability": <0-100 probability of rug pull>,
    "ai_verdict": "SAFE|CAUTION|RISKY|DANGEROUS|SCAM",
    "ai_summary": "<2-3 sentences: what is this token and main conclusion>",
    "ai_token_type": "MEMECOIN|UTILITY|DEFI|GOVERNANCE|SCAM|UNKNOWN",
    "ai_code_audit": "<contract security assessment>",
    "ai_whale_risk": "<whale/concentration risk assessment>",
    "ai_sentiment": "<social presence evaluation>",
    "ai_trading": "<trading activity analysis>",
    "ai_website_analysis": {{
        "quality": "professional|legitimate|neutral|suspicious|scam_likely",
        "professionalism_score": <0-10>,
        "concerns": ["<list of specific website concerns if any>"]
    }},
    "ai_red_flags": [
        {{"flag": "<description>", "severity": "CRITICAL|HIGH|MEDIUM|LOW"}},
        ...
    ],
    "ai_green_flags": [
        {{"flag": "<description>", "confidence": "HIGH|MEDIUM|LOW"}},
        ...
    ],
    "ai_recommendation": "<specific actionable advice for trader>",
    "ai_narrative": "<token type: memecoin|DeFi|utility|scam|unknown>"
}}

CRITICAL RULES:
- Be STRICT but FAIR - protect users while being objective
- Your ai_score IS the final score shown to users - make it count!
- Good security metrics (mint disabled, LP locked, socials present) = score 60+ minimum
- Critical security concerns (mint enabled, LP unlocked) = score appropriately low
- UNKNOWN LP lock status is missing evidence, not proof of unlocked liquidity
- Suspicious data (like 0% holder concentration) = flag it but don't over-penalize
- Token age alone should NOT significantly lower an otherwise strong token
- Be consistent: similar tokens should get similar scores
- Your analysis drives the user's investment decision!"""

        return prompt

    async def analyze(self, request: TokenAnalysisRequest) -> AIResponse:
        """
        Perform comprehensive AI-powered token analysis.

        Args:
            request: TokenAnalysisRequest with complete token data

        Returns:
            AIResponse with structured analysis results
        """
        start_time = time.time()

        # Generate trace ID for request tracking
        trace_id = generate_trace_id(request.symbol, "analyze")
        context = {
            "trace_id": trace_id,
            "symbol": request.symbol,
            "address": request.address
        }

        prompt = self._build_analysis_prompt(request)

        # Log request
        self.ai_logger.log_request(
            provider=self.provider.value,
            model=self.model,
            operation="analyze",
            prompt=prompt,
            params={
                "temperature": 0.1,
                "max_tokens": 2000,
                "top_p": 0.9
            },
            context=context
        )

        try:
            session = await self._ensure_session()

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Add OpenRouter-specific headers
            if self.use_openrouter:
                headers["HTTP-Referer"] = "https://t.me/Ilyon_AI_Bot"
                headers["X-Title"] = "Ilyon AI Bot"

            last_error_message = "API error"
            model_name = self.model

            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 2000,
                "top_p": 0.9
            }

            try:
                async with session.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=None),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        last_error_message = f"HTTP {resp.status}"
                        logger.warning(f"AI API error ({model_name}): {resp.status} - {error_text[:200]}")

                        self.ai_logger.log_error(
                            error=Exception(f"HTTP {resp.status}: {error_text[:100]}"),
                            provider=self.provider.value,
                            model=model_name,
                            operation="analyze",
                            context=context,
                            exit_code=AILogger.EXIT_API_ERROR
                        )
                        return self._create_error_response(last_error_message, start_time)

                    data = await resp.json()

                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

                if not content:
                    self.ai_logger.log_error(
                        error=Exception("Empty response from AI"),
                        provider=self.provider.value,
                        model=model_name,
                        operation="analyze",
                        context=context,
                        exit_code=AILogger.EXIT_EMPTY_RESPONSE
                    )
                    return self._create_error_response("Empty response", start_time)

                result = self._parse_ai_response(content)

                usage = data.get('usage', {})
                tokens_used = usage.get('total_tokens', 0)
                tokens_prompt = usage.get('prompt_tokens', 0)
                tokens_completion = usage.get('completion_tokens', 0)
                latency_ms = int((time.time() - start_time) * 1000)

                self.ai_logger.log_response(
                    success=True,
                    provider=self.provider.value,
                    model=model_name,
                    operation="analyze",
                    response_data=result,
                    raw_response=content if settings.log_ai_full_responses else None,
                    tokens_used=tokens_used,
                    tokens_prompt=tokens_prompt,
                    tokens_completion=tokens_completion,
                    latency_ms=latency_ms,
                    context=context,
                    exit_code=AILogger.EXIT_SUCCESS
                )

                logger.info(
                    f"AI Analysis complete ({model_name}): {request.symbol} | "
                    f"Score: {result.get('ai_score', 'N/A')} | "
                    f"Verdict: {result.get('ai_verdict', 'N/A')} | "
                    f"Rug%: {result.get('ai_rug_probability', 'N/A')}"
                )

                return AIResponse(
                    success=True,
                    provider=self.provider,
                    content=result,
                    raw_text=content,
                    model=model_name,
                    tokens_used=tokens_used,
                    latency_ms=latency_ms
                )
            except Exception as e:
                last_error_message = str(e) or "Unexpected error"
                logger.warning(f"AI API error for {model_name}: {e}")
                return self._create_error_response(last_error_message, start_time)

        except asyncio.TimeoutError as e:
            logger.error("AI API timeout")

            # Log timeout error
            self.ai_logger.log_error(
                error=e,
                provider=self.provider.value,
                model=self.model,
                operation="analyze",
                context=context,
                exit_code=AILogger.EXIT_TIMEOUT
            )

            return self._create_error_response("Timeout", start_time)

        except json.JSONDecodeError as e:
            logger.error(f"AI response parse error: {e}")

            # Log parse error
            self.ai_logger.log_error(
                error=e,
                provider=self.provider.value,
                model=self.model,
                operation="analyze",
                context=context,
                exit_code=AILogger.EXIT_PARSE_ERROR
            )

            return self._create_error_response("Parse error", start_time)

        except Exception as e:
            logger.error(f"AI analysis error: {e}")

            # Log general error
            self.ai_logger.log_error(
                error=e,
                provider=self.provider.value,
                model=self.model,
                operation="analyze",
                context=context,
                exit_code=AILogger.EXIT_API_ERROR
            )

            return self._create_error_response(str(e), start_time)

    def _repair_truncated_json(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to repair and extract data from truncated JSON responses.

        This handles cases where the AI response was cut off mid-generation,
        leaving incomplete JSON that can still yield useful partial data.

        Args:
            content: Truncated JSON string

        Returns:
            Partially recovered dict or None if repair failed
        """
        try:
            # Try to find and close any unterminated string
            # Common pattern: truncated in middle of a string value

            # Count brackets to understand structure
            open_braces = content.count('{') - content.count('}')
            open_brackets = content.count('[') - content.count(']')

            # Check if we're inside an unterminated string
            # by counting unescaped quotes
            in_string = False
            i = 0
            while i < len(content):
                if content[i] == '\\' and i + 1 < len(content):
                    i += 2  # Skip escaped character
                    continue
                if content[i] == '"':
                    in_string = not in_string
                i += 1

            repaired = content

            # If inside a string, close it
            if in_string:
                repaired += '...(truncated)"'

            # Close any open arrays
            repaired += ']' * open_brackets

            # Close any open objects
            repaired += '}' * open_braces

            # Try to parse the repaired JSON
            result = json.loads(repaired)
            logger.info(f"Successfully repaired truncated JSON response")
            return result

        except json.JSONDecodeError:
            # If simple repair failed, try extracting individual fields with regex
            try:
                extracted = {}

                # Extract numeric fields
                for field in ['ai_score', 'ai_confidence', 'ai_rug_probability']:
                    match = re.search(rf'"{field}"\s*:\s*(\d+)', content)
                    if match:
                        extracted[field] = int(match.group(1))

                # Extract string fields (take content up to next quote or truncation)
                for field in ['ai_verdict', 'ai_summary', 'ai_code_audit', 'ai_whale_risk',
                              'ai_sentiment', 'ai_trading', 'ai_recommendation', 'ai_narrative']:
                    match = re.search(rf'"{field}"\s*:\s*"([^"]*)', content)
                    if match:
                        value = match.group(1)
                        # Mark truncated values
                        if not content[match.end():match.end()+1] == '"':
                            value += '...(truncated)'
                        extracted[field] = value

                if extracted.get('ai_score') is not None:
                    logger.info(f"Extracted partial data from truncated response: score={extracted.get('ai_score')}")
                    return extracted

            except Exception:
                pass

            return None

    def _parse_ai_response(self, content: str) -> Dict[str, Any]:
        """
        Parse and validate AI JSON response.

        Args:
            content: Raw AI response text

        Returns:
            Validated dict with analysis results
        """
        try:
            content = content.strip()

            # Remove markdown code blocks if present
            if content.startswith('```'):
                content = re.sub(r'^```json?\n?', '', content)
                content = re.sub(r'\n?```$', '', content)

            result = json.loads(content)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response: {e} | Content: {content[:200]}")

            # Attempt to repair truncated JSON
            result = self._repair_truncated_json(content)
            if result is None:
                return self._default_analysis()

            logger.info("Using repaired/partial AI response data")

        # Validate and normalize scores
        result['ai_score'] = max(0, min(100, int(result.get('ai_score', 50))))
        result['ai_confidence'] = max(0, min(100, int(result.get('ai_confidence', result.get('confidence', 70)))))
        result['ai_rug_probability'] = max(0, min(100, int(result.get('ai_rug_probability', result.get('rug_probability', 50)))))

        # Normalize verdict field
        result['ai_verdict'] = result.get('ai_verdict', result.get('verdict', 'CAUTION')).upper()

        # Ensure required fields exist with ai_ prefix
        result.setdefault('ai_summary', result.get('summary', ''))
        result.setdefault('ai_code_audit', result.get('code_audit', ''))
        result.setdefault('ai_whale_risk', result.get('whale_risk', ''))
        result.setdefault('ai_sentiment', result.get('sentiment', ''))
        result.setdefault('ai_trading', result.get('trading_analysis', ''))
        result.setdefault('ai_recommendation', result.get('recommendation', ''))
        result.setdefault('ai_narrative', result.get('narrative', 'Unknown'))

        # Handle red/green flags (may be objects or strings)
        red_flags = result.get('ai_red_flags', result.get('red_flags', []))
        green_flags = result.get('ai_green_flags', result.get('green_flags', []))

        # Normalize flags to strings for display
        result['ai_red_flags'] = self._normalize_flags(red_flags)
        result['ai_green_flags'] = self._normalize_flags(green_flags)

        # Handle website analysis (may be dict or missing)
        website_analysis = result.get('ai_website_analysis', {})
        if isinstance(website_analysis, dict):
            result['ai_website_quality'] = website_analysis.get('quality', '')
            result['ai_website_professionalism'] = max(0, min(10, int(website_analysis.get('professionalism_score', 5))))
            concerns = website_analysis.get('concerns', [])
            result['ai_website_concerns'] = concerns if isinstance(concerns, list) else []
        else:
            result['ai_website_quality'] = ''
            result['ai_website_professionalism'] = 5
            result['ai_website_concerns'] = []

        return result

    def _normalize_flags(self, flags: list) -> list:
        """Normalize flags to strings, handling both dict and string formats."""
        normalized = []
        for flag in flags:
            if isinstance(flag, dict):
                # Extract flag text and optionally severity/confidence
                text = flag.get('flag', str(flag))
                severity = flag.get('severity', flag.get('confidence', ''))
                if severity:
                    normalized.append(f"{text} [{severity}]")
                else:
                    normalized.append(text)
            else:
                normalized.append(str(flag))
        return normalized

    def _default_analysis(self) -> Dict[str, Any]:
        """Return default analysis when AI fails"""
        return {
            "ai_score": 50,
            "ai_confidence": 30,
            "ai_rug_probability": 50,
            "ai_verdict": "CAUTION",
            "ai_summary": "AI analysis unavailable - manual verification required",
            "ai_code_audit": "Unable to verify",
            "ai_whale_risk": "Unable to assess",
            "ai_sentiment": "Unable to evaluate",
            "ai_trading": "Unable to analyze",
            "ai_red_flags": ["AI analysis unavailable"],
            "ai_green_flags": [],
            "ai_recommendation": "CAUTION: Do your own research (DYOR)",
            "ai_narrative": "Unknown",
            "ai_website_quality": "",
            "ai_website_professionalism": 5,
            "ai_website_concerns": []
        }

    def _create_error_response(self, error: str, start_time: float) -> AIResponse:
        """Create error AIResponse with default analysis"""
        return AIResponse(
            success=False,
            provider=self.provider,
            content=self._default_analysis(),
            raw_text="",
            model=self.model,
            tokens_used=0,
            latency_ms=int((time.time() - start_time) * 1000),
            error=error
        )

    async def chat(self, message: str, system_prompt: str = "") -> str:
        """
        General AI chat for user questions.

        Args:
            message: User message
            system_prompt: Optional system prompt override

        Returns:
            AI response text
        """
        try:
            session = await self._ensure_session()

            if not system_prompt:
                system_prompt = """You are Ilyon AI, a STRICT cryptocurrency and Solana blockchain expert.
Answer concisely and directly.
Always warn about risks.
If asked about a specific token, suggest sending the address for analysis."""

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            if self.use_openrouter:
                headers["HTTP-Referer"] = "https://t.me/Ilyon_AI_Bot"
                headers["X-Title"] = "Ilyon AI Bot"

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                "temperature": 0.7,
                "max_tokens": 300
            }

            async with session.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return "Sorry, I can't respond right now. Please try again later."

                data = await resp.json()
                return data.get('choices', [{}])[0].get('message', {}).get('content', 'No response')

        except Exception as e:
            logger.error(f"Chat error: {e}")
            return "An error occurred. Please try again."

    async def chat_json(
        self,
        message: str,
        system_prompt: str = "",
        max_tokens: int = 900,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        """Structured JSON chat helper for deterministic integrations."""
        try:
            session = await self._ensure_session()

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            if self.use_openrouter:
                headers["HTTP-Referer"] = "https://t.me/Ilyon_AI_Bot"
                headers["X-Title"] = "Ilyon AI Bot"

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }

            async with session.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=None),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.warning("Structured chat API error: %s - %s", resp.status, error_text[:300])
                    return {}

                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    return {}
                return self._extract_json_from_text(content)

        except Exception as e:
            logger.warning("Structured chat error: %s", e)
            return {}

    def _extract_json_from_text(self, raw_text: str) -> Dict[str, Any]:
        text = (raw_text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start:end + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
        return {}
