"""
Solana token analyzer orchestrator.

This module coordinates all data collection, AI analysis, and scoring
for comprehensive Solana token analysis. Integrates DexScreener, RugCheck,
Solana RPC, website scraping, AI analysis, and scoring algorithms.

NOTE: This analyzer is exclusively for Solana blockchain tokens.
All data providers and analysis methods are Solana-specific.

Features:
- Developer Wallet Forensics for Solana token deployers
- Behavioral Anomaly Detection for predictive rug detection
- Honeypot detection via Jupiter swap simulation
"""

import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

from src.core.models import TokenInfo, AnalysisResult
from src.core.scorer import TokenScorer
from src.config import settings
from src.data.dexscreener import DexScreenerClient
from src.data.rugcheck import RugCheckClient
from src.data.solana import SolanaClient
from src.data.scraper import WebsiteScraper
from src.ai.router import AIRouter, MultiAIResult

# NEW: Advanced analytics imports
from src.analytics.wallet_forensics import WalletForensicsEngine, get_token_deployer
from src.analytics.anomaly_detector import BehavioralAnomalyDetector
from src.analytics.time_series import TimeSeriesCollector

# Honeypot detection
from src.data.honeypot import HoneypotDetector

logger = logging.getLogger(__name__)


class TokenAnalyzer:
    """
    Main Solana token analysis orchestrator.

    Coordinates data collection from multiple Solana-specific sources,
    runs AI analysis, and calculates comprehensive risk scores.

    NOTE: Exclusively for Solana blockchain - does not support other chains.

    Architecture:
    1. Parallel data collection (DexScreener, RugCheck, Solana RPC, Website)
    2. AI analysis via OpenRouter
    3. Risk scoring with metric-AI balance
    4. Results caching for performance

    Usage:
        analyzer = TokenAnalyzer()
        result = await analyzer.analyze(address, mode="standard")
    """

    def __init__(
        self,
        dex_client: Optional[DexScreenerClient] = None,
        rugcheck_client: Optional[RugCheckClient] = None,
        solana_client: Optional[SolanaClient] = None,
        scraper: Optional[WebsiteScraper] = None,
        ai_router: Optional[AIRouter] = None,
        scorer: Optional[TokenScorer] = None,
        forensics_engine: Optional[WalletForensicsEngine] = None,
        anomaly_detector: Optional[BehavioralAnomalyDetector] = None,
        honeypot_detector: Optional[HoneypotDetector] = None
    ):
        """
        Initialize token analyzer with data clients.

        Args:
            dex_client: Optional DexScreener client
            rugcheck_client: Optional RugCheck client
            solana_client: Optional Solana RPC client
            scraper: Optional website scraper
            ai_router: Optional AI router
            scorer: Optional token scorer
            forensics_engine: Optional wallet forensics engine
            anomaly_detector: Optional behavioral anomaly detector
            honeypot_detector: Optional honeypot detector
        """
        self.dex = dex_client or DexScreenerClient()
        self.rugcheck = rugcheck_client or RugCheckClient()
        self.solana = solana_client or SolanaClient(
            settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key
        )
        self.scraper = scraper or WebsiteScraper()
        self.ai_router = ai_router or AIRouter()
        self.scorer = scorer or TokenScorer()

        # NEW: Advanced analytics engines
        self.forensics = forensics_engine or WalletForensicsEngine(
            solana_rpc_url=settings.solana_rpc_url
        )
        self.time_series = TimeSeriesCollector()
        self.anomaly_detector = anomaly_detector or BehavioralAnomalyDetector(
            time_series_collector=self.time_series
        )

        # Honeypot detection via Jupiter simulation
        self.honeypot_detector = honeypot_detector or HoneypotDetector(
            solana_client=self.solana,
            rpc_url=settings.solana_rpc_url
        )

        # Simple in-memory cache (replace with Redis in production)
        self._cache: Dict[str, AnalysisResult] = {}

        logger.info("✅ TokenAnalyzer initialized with advanced analytics + honeypot detection")

    def is_valid_address(self, address: str) -> bool:
        """
        Validate Solana address format.

        Args:
            address: Solana address string

        Returns:
            True if valid Solana address
        """
        return self.solana.is_valid_address(address)

    async def analyze(
        self,
        address: str,
        mode: str = "standard"
    ) -> Optional[AnalysisResult]:
        """
        Analyze a token with full data collection and AI analysis.

        Args:
            address: Solana token contract address
            mode: Analysis mode ("quick", "standard", or "full")

        Returns:
            AnalysisResult with scores and recommendation, or None if failed

        Modes:
            - "quick": GPT-4o-mini only (~5 seconds)
            - "standard" / "full": Full data + primary model (~15 seconds)
        """
        # Check cache
        cache_key = f"{address}:{mode}"
        if cache_key in self._cache:
            logger.info(f"✅ Cache hit for {address[:8]}... ({mode})")
            return self._cache[cache_key]

        logger.info(f"🔍 Starting {mode.upper()} analysis for {address[:8]}...")

        try:
            # Create token info object
            token = TokenInfo(address=address)

            # Stage 1: Parallel data collection
            logger.info("📊 Stage 1: Collecting data from all sources...")
            await self._collect_data(token)

            # Stage 2: AI analysis (mode-dependent)
            logger.info(f"🤖 Stage 2: Running {mode} AI analysis...")
            ai_results = await self.ai_router.analyze(token, mode=mode)

            # Stage 3: Apply AI results to token
            logger.info("📝 Stage 3: Applying AI results...")
            self._apply_ai_results(token, ai_results)

            # Stage 4: Calculate scores
            logger.info("📊 Stage 4: Calculating risk scores...")
            result = self.scorer.calculate(token)

            # Cache result
            self._cache[cache_key] = result

            logger.info(
                f"✅ Analysis complete for {token.symbol}: "
                f"Score={result.overall_score}, Grade={result.grade}"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Analysis failed for {address[:8]}: {e}", exc_info=True)
            return None

    async def _collect_data(self, token: TokenInfo) -> None:
        """
        Collect data from all sources in parallel.

        Runs DexScreener, RugCheck, Solana RPC, and website scraper
        concurrently for maximum speed.

        Args:
            token: TokenInfo object to populate with data
        """
        # Run all data collection in parallel
        tasks = {
            'dex': self.dex.get_token(token.address),
            'rugcheck': self.rugcheck.check_token(token.address),
            'onchain': self.solana.get_onchain_data(token.address),
            'holders': self.solana.get_top_holders(token.address, limit=20),
        }

        results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True
        )

        # Map results back
        data = dict(zip(tasks.keys(), results))

        # Log errors but continue
        for key, result in data.items():
            if isinstance(result, Exception):
                logger.warning(f"⚠️ {key.capitalize()} data collection failed: {result}")

        # Apply DexScreener data
        if not isinstance(data['dex'], Exception) and data['dex']:
            self._apply_dex_data(token, data['dex'])
        else:
            logger.warning(f"⚠️ No DexScreener data for {token.symbol}")

        # Apply RugCheck data
        if not isinstance(data['rugcheck'], Exception) and data['rugcheck']:
            self._apply_rugcheck_data(token, data['rugcheck'])

        # Apply on-chain data
        if not isinstance(data['onchain'], Exception) and data['onchain']:
            self._apply_onchain_data(token, data['onchain'])

        # Apply holder data and analyze
        if not isinstance(data['holders'], Exception) and data['holders']:
            token.top_holders = data['holders']
            await self.solana.analyze_holder_distribution(token)

        # Scrape website if available
        if token.has_website and token.website_url:
            await self._scrape_website(token)

        # NEW: Run advanced analytics in parallel
        await self._run_advanced_analytics(token)

    async def _run_advanced_analytics(self, token: TokenInfo) -> None:
        """
        Run advanced analytics: wallet forensics, anomaly detection, and honeypot check.

        These provide:
        1. Developer wallet reputation (cross-token scammer detection)
        2. Behavioral anomaly detection (predictive rug warning)
        3. Honeypot detection (sell simulation)
        """
        try:
            # Run forensics, anomaly detection, and honeypot check in parallel
            forensics_task = self._run_forensics(token)
            anomaly_task = self._run_anomaly_detection(token)
            honeypot_task = self._run_honeypot_detection(token)

            await asyncio.gather(
                forensics_task,
                anomaly_task,
                honeypot_task,
                return_exceptions=True
            )

        except Exception as e:
            logger.warning(f"⚠️ Advanced analytics error: {e}")

    async def _run_forensics(self, token: TokenInfo) -> None:
        """
        Run deployer wallet forensics analysis.

        Identifies serial scammers by tracking wallet history across tokens.
        """
        try:
            # Get deployer wallet
            deployer = await get_token_deployer(
                token.address,
                settings.solana_rpc_url
            )

            if not deployer:
                logger.debug(f"Could not find deployer for {token.symbol}")
                return

            token.deployer_address = deployer

            # Run forensics analysis
            forensics_result = await self.forensics.analyze_wallet(deployer)

            # Apply results to token
            token.deployer_reputation_score = forensics_result.reputation_score
            token.deployer_risk_level = forensics_result.risk_level.value
            token.deployer_tokens_deployed = forensics_result.tokens_deployed
            token.deployer_rugged_tokens = forensics_result.rugged_tokens
            token.deployer_rug_percentage = forensics_result.rug_percentage
            token.deployer_patterns_detected = forensics_result.patterns_detected
            token.deployer_is_known_scammer = (
                forensics_result.risk_level.value == "KNOWN_SCAMMER"
            )
            token.deployer_evidence_summary = forensics_result.evidence_summary
            token.deployer_forensics_available = True

            logger.info(
                f"🔍 Forensics for {token.symbol}: "
                f"Deployer={deployer[:8]}..., "
                f"Reputation={forensics_result.reputation_score:.0f}, "
                f"Risk={forensics_result.risk_level.value}"
            )

        except Exception as e:
            logger.warning(f"⚠️ Forensics analysis failed for {token.symbol}: {e}")
            token.deployer_forensics_available = False

    async def _run_anomaly_detection(self, token: TokenInfo) -> None:
        """
        Run behavioral anomaly detection for predictive rug warnings.

        Uses time-series analysis to identify pre-rug patterns.
        """
        try:
            # Run anomaly detection
            anomaly_result = await self.anomaly_detector.analyze_token(token.address)

            # Apply results to token
            token.anomaly_score = anomaly_result.anomaly_score
            token.anomaly_rug_probability = anomaly_result.rug_probability
            token.anomaly_time_to_rug = anomaly_result.time_to_rug_estimate
            token.anomaly_severity = anomaly_result.severity_level.value
            token.anomalies_detected = anomaly_result.anomalies_detected
            token.anomaly_recommendation = anomaly_result.recommendation
            token.anomaly_data_quality = anomaly_result.data_quality_score
            token.anomaly_confidence = anomaly_result.confidence
            token.anomaly_available = True

            logger.info(
                f"📊 Anomaly detection for {token.symbol}: "
                f"Score={anomaly_result.anomaly_score:.0f}, "
                f"RugProb={anomaly_result.rug_probability:.0f}%, "
                f"Severity={anomaly_result.severity_level.value}"
            )

            # Log critical warnings
            if anomaly_result.severity_level.value in ["CRITICAL", "HIGH"]:
                logger.warning(
                    f"⚠️ HIGH RISK ANOMALY for {token.symbol}: "
                    f"{anomaly_result.recommendation}"
                )

        except Exception as e:
            logger.warning(f"⚠️ Anomaly detection failed for {token.symbol}: {e}")
            token.anomaly_available = False

    async def _run_honeypot_detection(self, token: TokenInfo) -> None:
        """
        Run honeypot detection via Jupiter sell simulation.

        Simulates selling 0.1 SOL worth of tokens to detect:
        - Honeypots (tokens that cannot be sold)
        - High tax tokens (>20% sell tax)
        - Extreme tax tokens (>50% sell tax)
        """
        try:
            # Need token price to calculate amount to simulate
            if token.price_usd <= 0:
                logger.debug(f"Skipping honeypot check for {token.symbol} - no price data")
                token.honeypot_status = "unable_to_verify"
                token.honeypot_explanation = "Cannot verify - missing price data"
                return

            # Get SOL price for calculation (use approximation if not available)
            sol_price = await self._get_sol_price()

            # Run honeypot detection
            result = await self.honeypot_detector.check(
                token_address=token.address,
                token_decimals=token.decimals,
                token_price_usd=token.price_usd,
                sol_price_usd=sol_price
            )

            # Apply results to token
            token.honeypot_status = result.status.value
            token.honeypot_is_honeypot = result.is_honeypot
            token.honeypot_confidence = result.confidence
            token.honeypot_sell_tax_percent = result.sell_tax_percent
            token.honeypot_route_available = result.route_available
            token.honeypot_route_dex = result.route_dex
            token.honeypot_price_impact = result.price_impact_pct
            token.honeypot_warnings = result.warnings
            token.honeypot_explanation = result.explanation
            token.honeypot_checked = True

            # Log result
            if result.is_honeypot:
                logger.warning(
                    f"🍯 HONEYPOT DETECTED for {token.symbol}: {result.explanation}"
                )
            elif result.status.value in ["high_tax", "extreme_tax"]:
                logger.warning(
                    f"💸 High tax for {token.symbol}: {result.sell_tax_percent:.1f}%"
                )
            else:
                logger.info(
                    f"✅ Honeypot check for {token.symbol}: {result.status.value}"
                )

        except Exception as e:
            logger.warning(f"⚠️ Honeypot detection failed for {token.symbol}: {e}")
            token.honeypot_status = "error"
            token.honeypot_checked = False

    async def _get_sol_price(self) -> float:
        """
        Get current SOL price in USD.

        Uses DexScreener to fetch SOL price for honeypot calculations.
        Falls back to a reasonable default if unavailable.
        """
        try:
            # SOL wrapped token address
            sol_mint = "So11111111111111111111111111111111111111112"
            sol_data = await self.dex.get_token(sol_mint)
            if sol_data and sol_data.get('main'):
                price = float(sol_data['main'].get('priceUsd', 0))
                if price > 0:
                    return price
        except Exception as e:
            logger.debug(f"Could not fetch SOL price: {e}")

        # Fallback to reasonable default
        return 150.0

    def _apply_dex_data(self, token: TokenInfo, dex_data: Dict) -> None:
        """
        Apply DexScreener data to token.

        Extracts price, liquidity, volume, social links, and metadata.

        Args:
            token: TokenInfo to populate
            dex_data: DexScreener API response
        """
        if not dex_data or not dex_data.get('main'):
            return

        p = dex_data['main']

        # Basic token info
        base = p.get('baseToken', {})
        token.name = base.get('name', 'Unknown')
        token.symbol = base.get('symbol', '???')

        # Price and market data
        token.price_usd = float(p.get('priceUsd') or 0)
        token.market_cap = float(p.get('marketCap') or 0)
        token.fdv = float(p.get('fdv') or 0)

        # Liquidity
        liq = p.get('liquidity', {})
        token.liquidity_usd = float(liq.get('usd') or 0)

        # DexScreener LP lock check (fallback)
        labels = p.get('labels', [])
        if any('lock' in str(l).lower() for l in labels):
            token.liquidity_locked = True
        if p.get('boosts', {}).get('active'):
            token.liquidity_locked = True

        # Social media extraction
        info = p.get('info', {})
        if info:
            token.logo_url = info.get('imageUrl')

            # Socials
            socials = info.get('socials', [])
            for s in socials:
                social_type = s.get('type', '').lower()
                social_url = s.get('url', '')

                if social_type == 'twitter' or 'twitter.com' in social_url or 'x.com' in social_url:
                    token.has_twitter = True
                    token.twitter_url = social_url
                elif social_type == 'telegram' or 't.me' in social_url:
                    token.has_telegram = True
                    token.telegram_url = social_url

            # Websites
            websites = info.get('websites', [])
            if websites:
                token.has_website = True
                token.website_url = websites[0].get('url', '')

        # Count socials
        token.socials_count = sum([token.has_twitter, token.has_website, token.has_telegram])
        logger.info(
            f"📱 Socials for {token.symbol}: "
            f"Twitter={token.has_twitter}, "
            f"Website={token.has_website}, "
            f"Telegram={token.has_telegram}"
        )

        # Volume
        vol = p.get('volume', {})
        token.volume_24h = float(vol.get('h24') or 0)
        token.volume_1h = float(vol.get('h1') or 0)

        # Price changes
        pc = p.get('priceChange', {})
        token.price_change_24h = float(pc.get('h24') or 0)
        token.price_change_6h = float(pc.get('h6') or 0)
        token.price_change_1h = float(pc.get('h1') or 0)
        token.price_change_5m = float(pc.get('m5') or 0)

        # Transactions
        txns = p.get('txns', {}).get('h24', {})
        token.buys_24h = int(txns.get('buys') or 0)
        token.sells_24h = int(txns.get('sells') or 0)
        token.txns_24h = token.buys_24h + token.sells_24h

        # Pool info
        token.pair_address = p.get('pairAddress')
        token.dex_name = p.get('dexId', 'unknown').title()

        # Token age
        created = p.get('pairCreatedAt')
        if created:
            token.age_hours = (datetime.now() - datetime.fromtimestamp(created / 1000)).total_seconds() / 3600

        logger.info(
            f"✅ DexScreener data applied for {token.symbol}: "
            f"${token.price_usd:.8f}, "
            f"Liq=${token.liquidity_usd:,.0f}"
        )

    def _apply_rugcheck_data(self, token: TokenInfo, rugcheck_data: Dict) -> None:
        """
        Apply RugCheck LP lock verification data.

        Args:
            token: TokenInfo to populate
            rugcheck_data: RugCheck API response
        """
        # LP lock verification (highest priority)
        if rugcheck_data.get('lp_locked'):
            token.liquidity_locked = True
            token.lp_lock_percent = rugcheck_data.get('lp_lock_percent', 0)
            logger.info(f"🔒 LP Lock CONFIRMED via RugCheck for {token.symbol}")

        # RugCheck score and risks
        token.rugcheck_score = rugcheck_data.get('rugcheck_score', 0)
        token.rugcheck_risks = rugcheck_data.get('risks', [])

        logger.info(f"✅ RugCheck data applied for {token.symbol}")

    def _apply_onchain_data(self, token: TokenInfo, onchain_data: Dict) -> None:
        """
        Apply on-chain data from Solana RPC.

        Args:
            token: TokenInfo to populate
            onchain_data: Solana RPC response
        """
        token.mint_authority_enabled = onchain_data.get('mint_auth', True)
        token.freeze_authority_enabled = onchain_data.get('freeze_auth', True)
        token.supply = onchain_data.get('supply', 0)
        token.decimals = onchain_data.get('decimals', 9)

        logger.info(
            f"✅ On-chain data applied for {token.symbol}: "
            f"Mint={token.mint_authority_enabled}, "
            f"Freeze={token.freeze_authority_enabled}"
        )

    async def _scrape_website(self, token: TokenInfo) -> None:
        """
        Scrape and analyze token website with comprehensive quality scoring.

        Args:
            token: TokenInfo with website_url to scrape
        """
        logger.info(f"🌐 Scraping website for {token.symbol}...")

        try:
            website_data = await self.scraper.scrape_website(token.website_url)

            if website_data.get('success'):
                # Core website data
                token.website_content = website_data.get('content', '')[:2000]  # More content for AI
                token.website_title = website_data.get('title', '')
                token.website_description = website_data.get('description', '')
                token.website_red_flags = website_data.get('red_flags', [])
                token.website_load_time = website_data.get('load_time', 0)

                # Trust signals
                token.website_has_privacy_policy = website_data.get('has_privacy_policy', False)
                token.website_has_terms = website_data.get('has_terms', False)
                token.website_has_copyright = website_data.get('has_copyright', False)
                token.website_copyright_year = website_data.get('copyright_year')
                token.website_has_contact = website_data.get('has_contact_info', False)
                token.website_contact_email = website_data.get('contact_email')
                token.website_has_company_name = website_data.get('has_company_name', False)
                token.website_company_name = website_data.get('company_name')
                token.website_has_physical_address = website_data.get('has_physical_address', False)

                # Token integration signals
                token.website_has_contract_displayed = website_data.get('has_contract_address', False)
                token.website_contract_displayed = website_data.get('contract_displayed')
                token.website_has_tokenomics_numbers = website_data.get('has_tokenomics_numbers', False)
                token.website_tokenomics_details = website_data.get('tokenomics_details', [])
                token.website_has_buy_button = website_data.get('has_buy_button', False)
                token.website_buy_links = website_data.get('buy_links', [])
                token.website_has_audit = website_data.get('has_audit_mention', False)
                token.website_audit_provider = website_data.get('audit_provider')

                # Technical quality signals
                token.website_has_mobile_viewport = website_data.get('has_mobile_viewport', False)
                token.website_has_favicon = website_data.get('has_favicon', False)
                token.website_has_analytics = website_data.get('has_analytics', False)
                token.website_uses_modern_framework = website_data.get('uses_modern_framework', False)
                token.website_framework_detected = website_data.get('framework_detected')
                token.website_is_spa = website_data.get('is_spa', False)
                token.website_has_custom_domain = website_data.get('has_custom_domain', True)

                # Social presence
                token.website_social_links = website_data.get('social_links', {})
                token.website_has_discord = website_data.get('has_discord', False)
                token.website_has_medium = website_data.get('has_medium', False)
                token.website_has_github = website_data.get('has_github', False)

                # Section presence
                token.website_has_whitepaper = website_data.get('has_whitepaper', False)
                token.website_has_roadmap = website_data.get('has_roadmap', False)
                token.website_has_team = website_data.get('has_team', False)
                token.website_has_tokenomics = website_data.get('has_tokenomics', False)

                # Calculate granular quality score (0-100)
                token.website_quality = self._calculate_website_quality(website_data)

                # Legitimacy is based on score threshold
                token.website_is_legitimate = token.website_quality >= 45

                logger.info(
                    f"✅ Website scraped for {token.symbol}: "
                    f"Quality={token.website_quality}/100, "
                    f"Legitimate={token.website_is_legitimate}, "
                    f"Flags={len(token.website_red_flags)}, "
                    f"Trust={sum([token.website_has_privacy_policy, token.website_has_terms, token.website_has_copyright])}/3"
                )
            else:
                # Website failed to load
                token.website_quality = 0
                token.website_is_legitimate = False
                token.website_red_flags = [website_data.get('error', 'Сайт недоступен')]
                logger.warning(f"⚠️ Website failed for {token.symbol}: {website_data.get('error')}")

        except Exception as e:
            logger.error(f"Website scraping error for {token.symbol}: {e}")

    def _calculate_website_quality(self, website_data: dict) -> int:
        """
        Calculate comprehensive website quality score (0-100).

        Every point matters with this granular scoring system:
        - Content Substance (0-25): Length, title, description, sections
        - Trust Signals (0-20): Legal pages, contact, copyright, company
        - Token Integration (0-20): Contract displayed, tokenomics, buy links, audit
        - Technical Quality (0-15): HTTPS, load time, mobile, favicon, analytics
        - Professional Signals (0-15): Custom domain, social links
        - Red Flag Deductions (up to -30)

        Args:
            website_data: Dict from scraper with all extracted signals

        Returns:
            Quality score from 0-100
        """
        from datetime import datetime
        score = 0

        # ═══════════════════════════════════════════════════════════
        # CONTENT SUBSTANCE (0-25 points)
        # ═══════════════════════════════════════════════════════════

        content = website_data.get('content', '')
        content_len = len(content)

        # Check if this is an SPA/JS site with little content
        # This can happen when scraper can't execute JavaScript
        is_spa_with_low_content = (
            content_len < 200 and
            (website_data.get('uses_modern_framework', False) or
             website_data.get('is_spa', False) or
             content_len < 50)  # Very low content likely means JS rendering issue
        )

        # Content length scoring (0-15 points)
        if is_spa_with_low_content:
            # SPA detected - give base score as scraper can't read JS content
            score += 8
        elif content_len >= 3000:
            score += 15
        elif content_len >= 2000:
            score += 12
        elif content_len >= 1000:
            score += 9
        elif content_len >= 500:
            score += 6
        elif content_len >= 200:
            score += 3

        # Meaningful title (0-3 points)
        title = website_data.get('title', '')
        if title and len(title) > 10 and title.lower() != "untitled":
            score += 3
        elif title and len(title) > 5:
            score += 1

        # Meta description (0-3 points)
        description = website_data.get('description', '')
        if description and len(description) > 50:
            score += 3
        elif description and len(description) > 20:
            score += 1

        # Structured sections (0-4 points)
        if website_data.get('has_tokenomics'):
            score += 2
        if website_data.get('has_roadmap'):
            score += 1
        if website_data.get('has_team'):
            score += 1

        # ═══════════════════════════════════════════════════════════
        # TRUST SIGNALS (0-20 points)
        # ═══════════════════════════════════════════════════════════

        # Legal pages (0-6 points)
        if website_data.get('has_privacy_policy'):
            score += 3
        if website_data.get('has_terms'):
            score += 3

        # Contact info (0-4 points)
        if website_data.get('has_contact_info'):
            score += 2
        if website_data.get('contact_email'):
            score += 2

        # Copyright with current year (0-4 points)
        if website_data.get('has_copyright'):
            score += 2
            copyright_year = website_data.get('copyright_year')
            current_year = datetime.now().year
            if copyright_year and copyright_year >= current_year - 1:
                score += 2  # Current or last year = more trustworthy

        # Company/team name (0-3 points)
        if website_data.get('has_company_name'):
            score += 3

        # Physical address (0-3 points) - rare but highly trustworthy
        if website_data.get('has_physical_address'):
            score += 3

        # ═══════════════════════════════════════════════════════════
        # TOKEN INTEGRATION (0-20 points)
        # ═══════════════════════════════════════════════════════════

        # Contract address displayed (0-5 points)
        if website_data.get('has_contract_address'):
            score += 5

        # Tokenomics with numbers (0-5 points)
        if website_data.get('has_tokenomics_numbers'):
            score += 5
        elif website_data.get('has_tokenomics'):
            score += 2  # Has section but no specifics

        # Buy/swap functionality (0-4 points)
        if website_data.get('has_buy_button'):
            score += 2
        if len(website_data.get('buy_links', [])) > 0:
            score += 2

        # Audit mention (0-6 points) - strong signal
        if website_data.get('has_audit_mention'):
            score += 4
            if website_data.get('audit_provider'):
                score += 2  # Named auditor = stronger

        # ═══════════════════════════════════════════════════════════
        # TECHNICAL QUALITY (0-15 points)
        # ═══════════════════════════════════════════════════════════

        # HTTPS (0-4 points)
        url = website_data.get('url', '')
        if url.startswith('https://'):
            score += 4

        # Load time (0-4 points)
        load_time = website_data.get('load_time', 0)
        if load_time > 0:
            if load_time < 2.0:
                score += 4
            elif load_time < 3.5:
                score += 3
            elif load_time < 5.0:
                score += 2
            elif load_time < 8.0:
                score += 1

        # Mobile viewport (0-2 points)
        if website_data.get('has_mobile_viewport'):
            score += 2

        # Favicon (0-2 points)
        if website_data.get('has_favicon'):
            score += 2

        # Analytics (0-2 points)
        if website_data.get('has_analytics'):
            score += 2

        # Modern framework (0-1 point) - professional signal
        if website_data.get('uses_modern_framework'):
            score += 1

        # ═══════════════════════════════════════════════════════════
        # PROFESSIONAL SIGNALS (0-15 points)
        # ═══════════════════════════════════════════════════════════

        # Custom domain (0-5 points)
        if website_data.get('has_custom_domain', True):
            score += 5

        # Social presence on site (0-6 points)
        social_links = website_data.get('social_links', {})
        if 'twitter' in social_links:
            score += 2
        if 'telegram' in social_links:
            score += 2
        if website_data.get('has_discord') or 'discord' in social_links:
            score += 2

        # GitHub presence (0-2 points) - indicates development activity
        if website_data.get('has_github') or 'github' in social_links:
            score += 2

        # ═══════════════════════════════════════════════════════════
        # RED FLAG DEDUCTIONS (up to -20)
        # ═══════════════════════════════════════════════════════════

        red_flags = website_data.get('red_flags', [])

        # For SPA sites, filter out "very little content" flag (JS can't be scraped)
        if is_spa_with_low_content:
            red_flags = [f for f in red_flags if 'little content' not in f.lower()]

        # Graduated penalty based on flag count (reduced from previous harsh penalties)
        flag_count = len(red_flags)
        if flag_count >= 5:
            score -= 20  # Was -30
        elif flag_count >= 4:
            score -= 15  # Was -22
        elif flag_count >= 3:
            score -= 10  # Was -15
        elif flag_count >= 2:
            score -= 6   # Was -10
        elif flag_count == 1:
            score -= 3   # Was -5

        # Specific severe flag penalties (in addition to count)
        for flag in red_flags:
            flag_lower = flag.lower() if isinstance(flag, str) else ''
            if 'lorem ipsum' in flag_lower:
                score -= 10
                break
            if 'scam' in flag_lower or 'honeypot' in flag_lower:
                score -= 15
                break

        # Ensure bounds
        return max(0, min(100, score))

    def _apply_ai_results(self, token: TokenInfo, ai_results: MultiAIResult) -> None:
        """
        Apply AI analysis results to token.

        Args:
            token: TokenInfo to populate
            ai_results: MultiAIResult with AI response
        """
        # Apply AI results
        if ai_results.openai and ai_results.openai.success:
            token.ai_available = True
            content = ai_results.openai.content
            token.ai_score = content.get('ai_score', 50)
            token.ai_verdict = content.get('ai_verdict', 'CAUTION')
            token.ai_confidence = content.get('ai_confidence', 50)
            token.ai_rug_probability = content.get('ai_rug_probability', 50)
            token.ai_red_flags = content.get('ai_red_flags', [])
            token.ai_green_flags = content.get('ai_green_flags', [])
            token.ai_summary = content.get('ai_summary', '')
            token.ai_recommendation = content.get('ai_recommendation', '')
            token.ai_code_audit = content.get('ai_code_audit', '')
            token.ai_whale_risk = content.get('ai_whale_risk', '')
            token.ai_sentiment = content.get('ai_sentiment', '')
            token.ai_trading = content.get('ai_trading', '')
            token.ai_narrative = content.get('ai_narrative', '')
            # Map AI narrative to website type for display
            token.ai_website_type = token.ai_narrative if token.ai_narrative else "unknown"

            # Apply AI website assessment
            token.website_ai_quality = content.get('ai_website_quality', '')
            ai_concerns = content.get('ai_website_concerns', [])
            token.website_ai_concerns = ai_concerns if isinstance(ai_concerns, list) else []

            logger.info(
                f"✅ AI analysis applied: "
                f"Score={token.ai_score}, Verdict={token.ai_verdict}"
            )
        else:
            token.ai_available = False
            logger.warning(f"⚠️ AI analysis not available for {token.symbol}")

    async def close(self):
        """Cleanup all resources"""
        logger.info("🔄 Closing TokenAnalyzer...")

        await self.dex.close()
        await self.rugcheck.close()
        await self.solana.close()
        await self.scraper.close()
        await self.ai_router.close()
        await self.honeypot_detector.close()

        logger.info("✅ TokenAnalyzer closed")
