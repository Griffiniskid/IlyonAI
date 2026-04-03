"""
Universal token analyzer orchestrator.

This module coordinates all data collection, AI analysis, and scoring
for comprehensive multi-chain token analysis. Integrates chain-specific
data providers, AI analysis, and scoring algorithms.

Supported chains: Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche.

Features:
- Multi-chain token analysis with chain-specific risk factors
- Developer Wallet Forensics for token deployers
- Behavioral Anomaly Detection for predictive rug detection
- Honeypot detection via swap simulation (Jupiter for Solana, DEX routers for EVM)
- Smart contract scanning and AI-powered auditing
"""

import asyncio
import logging
from typing import Dict, Optional, cast
from datetime import datetime

from src.core.models import TokenInfo, AnalysisResult
from src.core.scorer import TokenScorer
from src.config import settings
from src.data.dexscreener import DexScreenerClient
from src.data.rugcheck import RugCheckClient
from src.data.solana import SolanaClient
from src.data.scraper import WebsiteScraper
from src.ai.router import AIRouter, MultiAIResult

# Multi-chain abstraction
from src.chains.address import AddressResolver
from src.chains.base import ChainType
from src.chains.registry import ChainRegistry

# NEW: Advanced analytics imports
from src.analytics.wallet_forensics import WalletForensicsEngine, get_token_deployer
from src.analytics.anomaly_detector import BehavioralAnomalyDetector
from src.analytics.time_series import TimeSeriesCollector

# Honeypot detection
from src.data.honeypot import HoneypotDetector

logger = logging.getLogger(__name__)


class TokenAnalyzer:
    """
    Universal multi-chain token analysis orchestrator.

    Coordinates data collection from chain-specific and universal data sources,
    runs AI analysis, and calculates comprehensive risk scores.

    Supported chains: Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche.

    Architecture:
    1. Chain detection and routing
    2. Parallel data collection (chain-specific + universal providers)
    3. AI analysis via OpenRouter/OpenAI
    4. Risk scoring with chain-aware metric weights
    5. Results caching for performance

    Usage:
        analyzer = TokenAnalyzer()
        result = await analyzer.analyze(address, chain="ethereum", mode="standard")
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
        self.dex = dex_client or DexScreenerClient()
        self.rugcheck = rugcheck_client or RugCheckClient()
        self.solana = solana_client or SolanaClient(
            settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key
        )
        self.scraper = scraper or WebsiteScraper()
        self.ai_router = ai_router or AIRouter()
        self.scorer = scorer or TokenScorer()

        # Advanced analytics engines
        self.forensics = forensics_engine or WalletForensicsEngine(
            solana_rpc_url=settings.solana_rpc_url
        )
        self.time_series = TimeSeriesCollector()
        self.anomaly_detector = anomaly_detector or BehavioralAnomalyDetector(
            time_series_collector=self.time_series
        )

        # Honeypot detection via Jupiter simulation (Solana)
        self.honeypot_detector = honeypot_detector or HoneypotDetector(
            solana_client=self.solana,
            rpc_url=settings.solana_rpc_url
        )

        # Address resolver for chain auto-detection
        self.address_resolver = AddressResolver()

        # Shared chain registry for all chain clients
        self.chain_registry = ChainRegistry()
        self.chain_registry.initialize(settings)

        # GoPlus client for EVM security data (lazy-initialized)
        self._goplus_client = None

        # Simple in-memory cache (replace with Redis in production)
        self._cache: Dict[str, AnalysisResult] = {}

        logger.info("TokenAnalyzer initialized — universal multi-chain mode")

    def _get_goplus_client(self):
        """Lazy-initialize GoPlus client."""
        if self._goplus_client is None:
            try:
                from src.data.goplus import GoPlusClient
                self._goplus_client = GoPlusClient()
            except Exception as e:
                logger.warning(f"GoPlus client unavailable: {e}")
        return self._goplus_client

    def is_valid_address(self, address: str) -> bool:
        """
        Validate address format for any supported chain.

        Args:
            address: Token contract address (Solana base58 or EVM 0x hex)

        Returns:
            True if valid address format
        """
        input_type = self.address_resolver.detect_input_type(address)
        return input_type in ("evm_address", "solana_address")

    def _resolve_chain(self, address: str, chain_hint: Optional[str] = None) -> ChainType:
        """
        Determine which chain to use for analysis.

        Priority:
        1. Explicit chain parameter
        2. Auto-detect from address format
        3. Default to Solana for base58 addresses

        Args:
            address: Token address
            chain_hint: Optional explicit chain name

        Returns:
            ChainType to use
        """
        if chain_hint:
            resolved = self.address_resolver.parse_chain_from_string(chain_hint)
            if resolved:
                return resolved
            logger.warning(f"Unknown chain hint '{chain_hint}', auto-detecting")

        detected = self.address_resolver.get_default_chain_for_address(address)
        if detected:
            return detected

        return ChainType.SOLANA

    async def analyze(
        self,
        address: str,
        mode: str = "standard",
        chain: Optional[str] = None
    ) -> Optional[AnalysisResult]:
        """
        Analyze a token with full data collection and AI analysis.

        Args:
            address: Token contract address (Solana or EVM)
            mode: Analysis mode ("quick", "standard", or "full")
            chain: Optional chain name — auto-detected from address if omitted

        Returns:
            AnalysisResult with scores and recommendation, or None if failed
        """
        # Resolve chain
        chain_type = self._resolve_chain(address, chain)

        # Check cache
        cache_key = f"{chain_type.value}:{address}:{mode}"
        if cache_key in self._cache:
            logger.info(f"Cache hit for {address[:8]}... ({mode}, {chain_type.value})")
            return self._cache[cache_key]

        logger.info(f"Starting {mode.upper()} analysis for {address[:8]}... on {chain_type.display_name}")

        try:
            # Create token info object with chain context
            token = TokenInfo(
                address=address,
                chain=chain_type.value,
                chain_id=chain_type.chain_id,
            )

            # Stage 1: Parallel data collection
            logger.info("Stage 1: Collecting data from all sources...")
            await self._collect_data(token, chain_type)

            # Stage 2: AI analysis (mode-dependent)
            logger.info(f"Stage 2: Running {mode} AI analysis...")
            ai_results = await self.ai_router.analyze(token, mode=mode)

            # Stage 3: Apply AI results to token
            logger.info("Stage 3: Applying AI results...")
            self._apply_ai_results(token, ai_results)

            # Stage 4: Calculate scores
            logger.info("Stage 4: Calculating risk scores...")
            result = self.scorer.calculate(token)

            # Cache result
            self._cache[cache_key] = result

            logger.info(
                f"Analysis complete for {token.symbol} on {chain_type.display_name}: "
                f"Score={result.overall_score}, Grade={result.grade}"
            )

            return result

        except Exception as e:
            logger.error(f"Analysis failed for {address[:8]}: {e}", exc_info=True)
            return None

    async def _collect_data(self, token: TokenInfo, chain_type: ChainType) -> None:
        """
        Collect data from all sources in parallel, routing by chain.

        Args:
            token: TokenInfo object to populate with data
            chain_type: Which chain this token is on
        """
        if chain_type == ChainType.SOLANA:
            await self._collect_solana_data(token)
        else:
            await self._collect_evm_data(token, chain_type)

        # Universal: website scraping
        if token.has_website and token.website_url:
            await self._scrape_website(token)

        # Advanced analytics — Solana only for now (forensics uses Solana RPC)
        if chain_type == ChainType.SOLANA:
            await self._run_advanced_analytics(token)

    async def _collect_solana_data(self, token: TokenInfo) -> None:
        """Collect data for a Solana token (existing flow)."""
        tasks = {
            'dex': self.dex.get_token(token.address),
            'rugcheck': self.rugcheck.check_token(token.address),
            'onchain': self.solana.get_onchain_data(token.address),
            'holders': self.solana.get_top_holders(token.address, limit=20),
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data = dict(zip(tasks.keys(), results))

        for key, result in data.items():
            if isinstance(result, Exception):
                logger.warning(f"{key.capitalize()} data collection failed: {result}")

        if not isinstance(data['dex'], Exception) and data['dex']:
            self._apply_dex_data(token, data['dex'])  # type: ignore[arg-type]

        if not isinstance(data['rugcheck'], Exception) and data['rugcheck']:
            self._apply_rugcheck_data(token, data['rugcheck'])  # type: ignore[arg-type]
            # Map rugcheck fields to universal fields
            token.can_mint = token.mint_authority_enabled
            token.can_pause = token.freeze_authority_enabled

        if not isinstance(data['onchain'], Exception) and data['onchain']:
            self._apply_onchain_data(token, data['onchain'])  # type: ignore[arg-type]

        if not isinstance(data['holders'], Exception) and data['holders']:
            token.top_holders = data['holders']  # type: ignore[assignment]
            await self.solana.analyze_holder_distribution(token)

    async def _collect_evm_data(self, token: TokenInfo, chain_type: ChainType) -> None:
        """Collect data for an EVM token using chain client + GoPlus."""
        dex_task = self.dex.get_token(token.address, chain=chain_type.value)
        goplus_task = self._collect_goplus_data(token, chain_type)
        evm_task = self._collect_evm_onchain_data(token, chain_type)

        dex_result, goplus_result, evm_result = await asyncio.gather(
            dex_task,
            goplus_task,
            evm_task,
            return_exceptions=True,
        )

        if isinstance(dex_result, Exception):
            logger.warning(f"DexScreener EVM fetch failed: {dex_result}")
        elif dex_result:
            self._apply_dex_data(token, cast(Dict, dex_result))

        if isinstance(goplus_result, Exception):
            logger.warning(f"GoPlus EVM fetch failed: {goplus_result}")

        if isinstance(evm_result, Exception):
            logger.warning(f"EVM on-chain fetch failed: {evm_result}")

        if token.liquidity_locked is None:
            token.liquidity_lock_note = (
                f"LP lock status is not currently verified for {chain_type.display_name}."
            )

    async def _collect_goplus_data(self, token: TokenInfo, chain_type: ChainType) -> None:
        """Fetch GoPlus security data for EVM tokens."""
        try:
            goplus = self._get_goplus_client()
            if not goplus:
                return

            data = await goplus.check_token_security(token.address, chain_type)
            if not data:
                return

            # Map GoPlus fields to TokenInfo
            token.goplus_is_honeypot = data.get('is_honeypot')
            token.goplus_buy_tax = data.get('buy_tax')
            token.goplus_sell_tax = data.get('sell_tax')
            token.goplus_is_mintable = data.get('is_mintable')
            token.goplus_can_blacklist = data.get('can_blacklist')
            token.goplus_can_pause = data.get('can_pause_transfer') or data.get('can_pause')
            token.goplus_is_proxy = data.get('is_proxy')
            token.goplus_owner_address = data.get('owner_address')
            token.goplus_creator_address = data.get('creator_address')
            token.transfer_pausable = bool(data.get('transfer_pausable') or data.get('can_pause_transfer'))
            token.is_open_source = bool(data.get('is_open_source'))

            # Map to universal fields
            token.can_mint = bool(data.get('is_mintable'))
            token.can_blacklist = bool(data.get('can_blacklist'))
            token.can_pause = bool(data.get('can_pause_transfer') or data.get('can_pause'))
            token.is_upgradeable = bool(data.get('is_proxy'))
            token.is_proxy_contract = bool(data.get('is_proxy'))
            token.is_renounced = data.get('owner_address', '').lower() in ('', '0x0000000000000000000000000000000000000000')
            token.deployer_address = data.get('creator_address')

            # Map to honeypot fields for unified display
            if token.goplus_is_honeypot is not None:
                token.honeypot_is_honeypot = token.goplus_is_honeypot
                token.honeypot_checked = True
                if token.goplus_is_honeypot:
                    token.honeypot_status = "honeypot"
                    token.honeypot_explanation = "GoPlus Security: confirmed honeypot"
                elif token.goplus_sell_tax and token.goplus_sell_tax > 50:
                    token.honeypot_status = "extreme_tax"
                    token.honeypot_sell_tax_percent = token.goplus_sell_tax
                elif token.goplus_sell_tax and token.goplus_sell_tax > 10:
                    token.honeypot_status = "high_tax"
                    token.honeypot_sell_tax_percent = token.goplus_sell_tax
                else:
                    token.honeypot_status = "safe"

            # Map mint authority (EVM equivalent)
            token.mint_authority_enabled = bool(data.get('is_mintable'))
            token.freeze_authority_enabled = bool(data.get('can_pause_transfer'))

            # Extract LP lock status from GoPlus lp_holders data
            lp_holders = data.get('lp_holders', [])
            if lp_holders:
                total_locked_pct = 0.0
                for lp in lp_holders:
                    is_locked = lp.get('is_locked') in (1, '1', True)
                    pct = float(lp.get('percent', 0) or 0) * 100  # GoPlus returns 0-1
                    if is_locked:
                        total_locked_pct += pct

                token.liquidity_lock_source = "GoPlus"
                if total_locked_pct > 0:
                    token.liquidity_locked = True
                    token.lp_lock_percent = min(total_locked_pct, 100.0)
                    token.liquidity_lock_note = f"LP lock verified via GoPlus ({token.lp_lock_percent:.0f}% locked)."
                else:
                    token.liquidity_locked = False
                    token.lp_lock_percent = 0
                    token.liquidity_lock_note = "GoPlus did not detect a verified LP lock."

            logger.info(f"GoPlus data applied for {token.address[:8]} on {chain_type.display_name}")

        except Exception as e:
            logger.warning(f"GoPlus data collection failed: {e}")

    async def _collect_evm_onchain_data(self, token: TokenInfo, chain_type: ChainType) -> None:
        """Fetch on-chain data from EVM RPC."""
        try:
            client = self.chain_registry.get_client(chain_type)
            if not client:
                return

            token_info = await client.get_token_info(token.address)
            if not token_info:
                return

            token.name = token_info.get('name', token.name)
            token.symbol = token_info.get('symbol', token.symbol)
            token.decimals = token_info.get('decimals', token.decimals)
            token.supply = token_info.get('total_supply', token_info.get('supply', token.supply))
            token.is_verified = token_info.get('is_verified')
            token.is_open_source = token_info.get('is_open_source', token.is_open_source)
            token.compiler_version = token_info.get('compiler_version')
            token.is_proxy_contract = token_info.get('is_proxy')
            token.proxy_implementation = token_info.get('proxy_implementation', token_info.get('implementation'))
            token.has_owner_function = token_info.get('has_owner_function')
            token.transfer_pausable = token_info.get('transfer_pausable', token.transfer_pausable)
            token.can_mint = bool(token_info.get('can_mint', token.can_mint))
            token.can_blacklist = bool(token_info.get('can_blacklist', token.can_blacklist))
            token.can_pause = bool(token_info.get('can_pause', token.can_pause))
            token.is_renounced = bool(token_info.get('is_renounced', token.is_renounced))

            if not token.deployer_address:
                try:
                    token.deployer_address = await client.get_deployer(token.address)
                except Exception as deployer_error:
                    logger.debug(f"Unable to resolve EVM deployer for {token.address[:8]}: {deployer_error}")

            # Holders (top 10)
            holders = await client.get_top_holders(token.address, limit=10)
            if holders:
                token.top_holders = holders
                # Calculate concentration
                if holders:
                    token.top_holder_pct = holders[0].get('percentage', 0) if holders else 0
                    top10_pct = sum(h.get('percentage', 0) for h in holders[:10])
                    token.holder_concentration = top10_pct

        except Exception as e:
            logger.warning(f"EVM on-chain data collection failed: {e}")

    async def _run_advanced_analytics(self, token: TokenInfo) -> None:
        """
        Run advanced analytics: wallet forensics, anomaly detection, and honeypot check.
        Currently Solana-only.
        """
        try:
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
            logger.warning(f"Advanced analytics error: {e}")

    async def _run_forensics(self, token: TokenInfo) -> None:
        """Run deployer wallet forensics analysis."""
        try:
            deployer = await get_token_deployer(
                token.address,
                settings.solana_rpc_url
            )

            if not deployer:
                logger.debug(f"Could not find deployer for {token.symbol}")
                return

            token.deployer_address = deployer

            forensics_result = await self.forensics.analyze_wallet(deployer)

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
                f"Forensics for {token.symbol}: "
                f"Deployer={deployer[:8]}..., "
                f"Reputation={forensics_result.reputation_score:.0f}, "
                f"Risk={forensics_result.risk_level.value}"
            )

        except Exception as e:
            logger.warning(f"Forensics analysis failed for {token.symbol}: {e}")
            token.deployer_forensics_available = False

    async def _run_anomaly_detection(self, token: TokenInfo) -> None:
        """Run behavioral anomaly detection for predictive rug warnings."""
        try:
            anomaly_result = await self.anomaly_detector.analyze_token(token.address)

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
                f"Anomaly detection for {token.symbol}: "
                f"Score={anomaly_result.anomaly_score:.0f}, "
                f"RugProb={anomaly_result.rug_probability:.0f}%, "
                f"Severity={anomaly_result.severity_level.value}"
            )

            if anomaly_result.severity_level.value in ["CRITICAL", "HIGH"]:
                logger.warning(
                    f"HIGH RISK ANOMALY for {token.symbol}: "
                    f"{anomaly_result.recommendation}"
                )

        except Exception as e:
            logger.warning(f"Anomaly detection failed for {token.symbol}: {e}")
            token.anomaly_available = False

    async def _run_honeypot_detection(self, token: TokenInfo) -> None:
        """Run honeypot detection via Jupiter sell simulation (Solana)."""
        try:
            if token.price_usd <= 0:
                logger.debug(f"Skipping honeypot check for {token.symbol} - no price data")
                token.honeypot_status = "unable_to_verify"
                token.honeypot_explanation = "Cannot verify - missing price data"
                return

            sol_price = await self._get_sol_price()

            result = await self.honeypot_detector.check(
                token_address=token.address,
                token_decimals=token.decimals,
                token_price_usd=token.price_usd,
                sol_price_usd=sol_price
            )

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

            if result.is_honeypot:
                logger.warning(f"HONEYPOT DETECTED for {token.symbol}: {result.explanation}")
            elif result.status.value in ["high_tax", "extreme_tax"]:
                logger.warning(f"High tax for {token.symbol}: {result.sell_tax_percent:.1f}%")
            else:
                logger.info(f"Honeypot check for {token.symbol}: {result.status.value}")

        except Exception as e:
            logger.warning(f"Honeypot detection failed for {token.symbol}: {e}")
            token.honeypot_status = "error"
            token.honeypot_checked = False

    async def _get_sol_price(self) -> float:
        """Get current SOL price in USD."""
        try:
            sol_mint = "So11111111111111111111111111111111111111112"
            sol_data = await self.dex.get_token(sol_mint)
            if sol_data and sol_data.get('main'):
                price = float(sol_data['main'].get('priceUsd', 0))
                if price > 0:
                    return price
        except Exception as e:
            logger.debug(f"Could not fetch SOL price: {e}")
        return 150.0

    def _apply_dex_data(self, token: TokenInfo, dex_data: Dict) -> None:
        """Apply DexScreener data to token."""
        if not dex_data or not dex_data.get('main'):
            return

        p = dex_data['main']

        base = p.get('baseToken', {})
        token.name = base.get('name', 'Unknown')
        token.symbol = base.get('symbol', '???')

        token.price_usd = float(p.get('priceUsd') or 0)
        token.market_cap = float(p.get('marketCap') or 0)
        token.fdv = float(p.get('fdv') or 0)

        liq = p.get('liquidity', {})
        token.liquidity_usd = float(liq.get('usd') or 0)

        info = p.get('info', {})
        if info:
            token.logo_url = info.get('imageUrl')

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

            websites = info.get('websites', [])
            if websites:
                token.has_website = True
                token.website_url = websites[0].get('url', '')

        token.socials_count = sum([token.has_twitter, token.has_website, token.has_telegram])

        vol = p.get('volume', {})
        token.volume_24h = float(vol.get('h24') or 0)
        token.volume_1h = float(vol.get('h1') or 0)

        pc = p.get('priceChange', {})
        token.price_change_24h = float(pc.get('h24') or 0)
        token.price_change_6h = float(pc.get('h6') or 0)
        token.price_change_1h = float(pc.get('h1') or 0)
        token.price_change_5m = float(pc.get('m5') or 0)

        txns = p.get('txns', {}).get('h24', {})
        token.buys_24h = int(txns.get('buys') or 0)
        token.sells_24h = int(txns.get('sells') or 0)
        token.txns_24h = token.buys_24h + token.sells_24h

        token.pair_address = p.get('pairAddress')
        token.dex_name = p.get('dexId', 'unknown').title()

        created = p.get('pairCreatedAt')
        if created:
            token.age_hours = (datetime.now() - datetime.fromtimestamp(created / 1000)).total_seconds() / 3600

        logger.info(
            f"DexScreener data applied for {token.symbol}: "
            f"${token.price_usd:.8f}, Liq=${token.liquidity_usd:,.0f}"
        )

    def _apply_rugcheck_data(self, token: TokenInfo, rugcheck_data: Dict) -> None:
        """Apply RugCheck LP lock verification data (Solana)."""
        token.liquidity_lock_source = "RugCheck"
        token.liquidity_locked = bool(rugcheck_data.get('lp_locked', False))
        if token.liquidity_locked:
            token.lp_lock_percent = rugcheck_data.get('lp_lock_percent', 0)
            token.liquidity_lock_note = "LP lock verified via RugCheck."
            logger.info(f"LP Lock CONFIRMED via RugCheck for {token.symbol}")
        else:
            token.lp_lock_percent = 0
            token.liquidity_lock_note = "RugCheck did not detect a verified LP lock."

        token.rugcheck_score = rugcheck_data.get('rugcheck_score', 0)
        token.rugcheck_risks = rugcheck_data.get('risks', [])

    def _apply_onchain_data(self, token: TokenInfo, onchain_data: Dict) -> None:
        """Apply on-chain data from Solana RPC."""
        token.mint_authority_enabled = onchain_data.get('mint_auth', True)
        token.freeze_authority_enabled = onchain_data.get('freeze_auth', True)
        token.supply = onchain_data.get('supply', 0)
        token.decimals = onchain_data.get('decimals', 9)
        # Map to universal fields
        token.can_mint = token.mint_authority_enabled
        token.can_pause = token.freeze_authority_enabled

    async def _scrape_website(self, token: TokenInfo) -> None:
        """Scrape and analyze token website."""
        logger.info(f"Scraping website for {token.symbol}...")

        try:
            website_data = await self.scraper.scrape_website(token.website_url or "")

            if website_data.get('success'):
                token.website_content = website_data.get('content', '')[:4000]
                token.website_title = website_data.get('title', '')
                token.website_description = website_data.get('description', '')
                token.website_red_flags = website_data.get('red_flags', [])
                token.website_load_time = website_data.get('load_time', 0)

                token.website_has_privacy_policy = website_data.get('has_privacy_policy', False)
                token.website_has_terms = website_data.get('has_terms', False)
                token.website_has_copyright = website_data.get('has_copyright', False)
                token.website_copyright_year = website_data.get('copyright_year')
                token.website_has_contact = website_data.get('has_contact_info', False)
                token.website_contact_email = website_data.get('contact_email')
                token.website_has_company_name = website_data.get('has_company_name', False)
                token.website_company_name = website_data.get('company_name')
                token.website_has_physical_address = website_data.get('has_physical_address', False)

                token.website_has_contract_displayed = website_data.get('has_contract_address', False)
                token.website_contract_displayed = website_data.get('contract_displayed')
                token.website_has_tokenomics_numbers = website_data.get('has_tokenomics_numbers', False)
                token.website_tokenomics_details = website_data.get('tokenomics_details', [])
                token.website_has_buy_button = website_data.get('has_buy_button', False)
                token.website_buy_links = website_data.get('buy_links', [])
                token.website_has_audit = website_data.get('has_audit_mention', False)
                token.website_audit_provider = website_data.get('audit_provider')

                token.website_has_mobile_viewport = website_data.get('has_mobile_viewport', False)
                token.website_has_favicon = website_data.get('has_favicon', False)
                token.website_has_analytics = website_data.get('has_analytics', False)
                token.website_uses_modern_framework = website_data.get('uses_modern_framework', False)
                token.website_framework_detected = website_data.get('framework_detected')
                token.website_is_spa = website_data.get('is_spa', False)
                token.website_has_custom_domain = website_data.get('has_custom_domain', False)

                token.website_social_links = website_data.get('social_links', {})
                token.website_has_discord = website_data.get('has_discord', False)
                token.website_has_medium = website_data.get('has_medium', False)
                token.website_has_github = website_data.get('has_github', False)

                token.website_has_whitepaper = website_data.get('has_whitepaper', False)
                token.website_has_roadmap = website_data.get('has_roadmap', False)
                token.website_has_team = website_data.get('has_team', False)
                token.website_has_tokenomics = website_data.get('has_tokenomics', False)

                token.website_quality = self._calculate_website_quality(website_data)
                token.website_is_legitimate = token.website_quality >= 45

                logger.info(
                    f"Website scraped for {token.symbol}: "
                    f"Quality={token.website_quality}/100, "
                    f"Legitimate={token.website_is_legitimate}"
                )
            else:
                token.website_quality = 0
                token.website_is_legitimate = False
                token.website_red_flags = [website_data.get('error', 'Website unavailable')]

        except Exception as e:
            logger.error(f"Website scraping error for {token.symbol}: {e}")

    def _calculate_website_quality(self, website_data: dict) -> int:
        """Calculate comprehensive website quality score (0-100)."""
        from datetime import datetime as dt
        score = 0

        content = website_data.get('content', '')
        content_len = len(content)

        is_spa_with_low_content = (
            content_len < 500 and
            (website_data.get('uses_modern_framework', False) or
             website_data.get('is_spa', False))
        )

        if is_spa_with_low_content:
            score += 10
        elif content_len >= 3000:
            score += 15
        elif content_len >= 1500:
            score += 13
        elif content_len >= 800:
            score += 11
        elif content_len >= 400:
            score += 8
        elif content_len >= 150:
            score += 5
        elif content_len >= 80:
            score += 3

        title = website_data.get('title', '')
        if title and len(title) > 5 and title.lower() != "untitled":
            score += 3
        elif title:
            score += 2

        description = website_data.get('description', '')
        if description and len(description) > 20:
            score += 3
        elif description:
            score += 2

        if website_data.get('has_tokenomics'): score += 2
        if website_data.get('has_roadmap'): score += 1
        if website_data.get('has_team'): score += 1

        if website_data.get('has_privacy_policy'): score += 3
        if website_data.get('has_terms'): score += 3
        if website_data.get('has_contact_info'): score += 2
        if website_data.get('contact_email'): score += 2

        if website_data.get('has_copyright'):
            score += 2
            copyright_year = website_data.get('copyright_year')
            current_year = dt.now().year
            if copyright_year and copyright_year >= current_year - 1:
                score += 2

        if website_data.get('has_company_name'): score += 3
        if website_data.get('has_physical_address'): score += 3

        if website_data.get('has_contract_address'): score += 5
        if website_data.get('has_tokenomics_numbers'):
            score += 5
        elif website_data.get('has_tokenomics'):
            score += 2

        if website_data.get('has_buy_button'): score += 2
        if len(website_data.get('buy_links', [])) > 0: score += 2

        if website_data.get('has_audit_mention'):
            score += 4
            if website_data.get('audit_provider'): score += 2

        url = website_data.get('url', '')
        if url.startswith('https://'): score += 4

        load_time = website_data.get('load_time', 0)
        if load_time > 0:
            if load_time < 2.0: score += 4
            elif load_time < 3.5: score += 3
            elif load_time < 5.0: score += 2
            elif load_time < 8.0: score += 1

        if website_data.get('has_mobile_viewport'): score += 2
        if website_data.get('has_favicon'): score += 2
        if website_data.get('has_analytics'): score += 2
        if website_data.get('uses_modern_framework'): score += 1

        if website_data.get('has_custom_domain', False): score += 5

        social_links = website_data.get('social_links', {})
        if 'twitter' in social_links: score += 2
        if 'telegram' in social_links: score += 2
        if website_data.get('has_discord') or 'discord' in social_links: score += 2
        if website_data.get('has_github') or 'github' in social_links: score += 2

        red_flags = website_data.get('red_flags', [])
        if is_spa_with_low_content:
            red_flags = [f for f in red_flags if 'little content' not in f.lower()]

        flag_count = len(red_flags)
        if flag_count >= 5: score -= 8
        elif flag_count >= 4: score -= 6
        elif flag_count >= 3: score -= 4
        elif flag_count >= 2: score -= 2
        elif flag_count == 1: score -= 1

        for flag in red_flags:
            flag_lower = flag.lower() if isinstance(flag, str) else ''
            if 'lorem ipsum' in flag_lower: score -= 3
            elif 'scam' in flag_lower or 'honeypot' in flag_lower: score -= 10
            elif 'broken link' in flag_lower: score -= 1

        return max(0, min(100, score))

    def _apply_ai_results(self, token: TokenInfo, ai_results: MultiAIResult) -> None:
        """Apply AI analysis results to token."""
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
            token.ai_website_type = content.get('ai_token_type') or token.ai_narrative or "unknown"

            token.website_ai_quality = content.get('ai_website_quality', '')
            ai_concerns = content.get('ai_website_concerns', [])
            token.website_ai_concerns = ai_concerns if isinstance(ai_concerns, list) else []

            logger.info(f"AI analysis applied: Score={token.ai_score}, Verdict={token.ai_verdict}")
        else:
            token.ai_available = False
            logger.warning(f"AI analysis not available for {token.symbol}")

        if ai_results.grok and ai_results.grok.success:
            grok_content = ai_results.grok.content

            if hasattr(token, 'grok_analysis'):
                token.grok_analysis = grok_content

            narrative_score = grok_content.get('narrative_score', 50)
            sentiment = grok_content.get('sentiment', 'NEUTRAL')
            summary = grok_content.get('narrative_summary', '')
            trending = grok_content.get('trending_status', 'NORMAL')
            category = grok_content.get('narrative_category', 'Uncategorized')
            vibe = grok_content.get('community_vibe', 'UNKNOWN')
            organic = grok_content.get('organic_score', 0)

            score_emoji = "🔥" if narrative_score >= 80 else "😐" if narrative_score >= 50 else "💀"

            narrative_block = f"""
🐦 <b>GROK NARRATIVE REPORT</b>
• <b>Score:</b> {score_emoji} {narrative_score}/100 ({trending})
• <b>Meta:</b> {category}
• <b>Vibe:</b> {vibe}
• <b>Organic:</b> {organic}/100

📝 <b>The Word on X:</b>
{summary}

🗣 <b>Influencer Activity:</b>
{grok_content.get('influencer_activity', 'No major activity detected.')}

⚠️ <b>FUD Warnings:</b>
{', '.join(grok_content.get('fud_warnings', ['None']))}
"""
            token.ai_narrative = narrative_block
            token.ai_sentiment = f"🐦 {sentiment} | Organic: {organic}%"

            logger.info(f"Grok narrative applied: Score={narrative_score}, Sentiment={sentiment}")

    async def close(self):
        """Cleanup all resources"""
        logger.info("Closing TokenAnalyzer...")

        await self.dex.close()
        await self.rugcheck.close()
        await self.solana.close()
        await self.scraper.close()
        await self.ai_router.close()
        await self.honeypot_detector.close()

        logger.info("TokenAnalyzer closed")
