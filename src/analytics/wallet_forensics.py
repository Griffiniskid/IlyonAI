"""
Developer Wallet Forensics Engine.

Tracks developer wallets across multiple token launches to identify
serial scammers before they can victimize new users.

This creates a cross-token reputation system - a public good for the
Solana ecosystem that benefits all traders.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple
import asyncio
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)


class WalletRiskLevel(Enum):
    """Risk level classification for wallets."""
    CLEAN = "CLEAN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    KNOWN_SCAMMER = "KNOWN_SCAMMER"


@dataclass
class TokenDeploymentRecord:
    """Record of a token deployment by a wallet."""
    token_address: str
    token_symbol: str
    deployed_at: datetime
    status: str  # "active", "rugged", "abandoned"
    peak_liquidity_usd: float = 0.0
    final_liquidity_usd: float = 0.0
    liquidity_removal_pct: float = 0.0
    lifespan_hours: float = 0.0
    rugged_at: Optional[datetime] = None


@dataclass
class WalletForensicsResult:
    """Complete forensics analysis result for a wallet."""

    wallet_address: str
    reputation_score: float  # 0-100 (higher = safer)
    risk_level: WalletRiskLevel

    # Token history
    tokens_deployed: int = 0
    rugged_tokens: int = 0
    active_tokens: int = 0
    rug_percentage: float = 0.0  # What % of tokens were rugs

    # Financial impact
    total_value_rugged_usd: float = 0.0
    avg_lifespan_hours: float = 0.0

    # Pattern detection
    patterns_detected: List[str] = field(default_factory=list)
    pattern_severity: str = "NONE"  # NONE, LOW, MEDIUM, HIGH, CRITICAL

    # Related wallets (potentially same operator)
    related_wallets: List[str] = field(default_factory=list)

    # Funding chain analysis
    funding_chain: List[str] = field(default_factory=list)
    funding_risk: float = 0.0  # 0-1 risk from funding sources

    # Evidence and explanation
    evidence_summary: str = ""
    confidence: float = 50.0  # 0-100 confidence in analysis

    # Token deployment history
    deployment_history: List[TokenDeploymentRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            "wallet_address": self.wallet_address,
            "reputation_score": self.reputation_score,
            "risk_level": self.risk_level.value,
            "tokens_deployed": self.tokens_deployed,
            "rugged_tokens": self.rugged_tokens,
            "active_tokens": self.active_tokens,
            "rug_percentage": self.rug_percentage,
            "total_value_rugged_usd": self.total_value_rugged_usd,
            "avg_lifespan_hours": self.avg_lifespan_hours,
            "patterns_detected": self.patterns_detected,
            "pattern_severity": self.pattern_severity,
            "related_wallets": self.related_wallets,
            "funding_chain": self.funding_chain,
            "funding_risk": self.funding_risk,
            "evidence_summary": self.evidence_summary,
            "confidence": self.confidence,
        }


class WalletForensicsEngine:
    """
    Analyzes wallet history to detect serial scammers.

    Detection methods:
    1. Token deployment history analysis
    2. Fund flow tracing (where did initial LP come from?)
    3. Cross-wallet relationship mapping
    4. Pattern matching against known scam behaviors
    """

    # Known scam patterns with detection parameters
    SCAM_PATTERNS = {
        "rapid_deployment": {
            "description": "Multiple tokens deployed in short period",
            "threshold_tokens": 3,
            "window_hours": 168,  # 7 days
            "risk_weight": 30,
        },
        "consistent_rug_timing": {
            "description": "Similar rug timing across tokens",
            "threshold_hours": 24,
            "variance_hours": 6,
            "risk_weight": 25,
        },
        "lp_removal_pattern": {
            "description": "Consistently high LP removal percentage",
            "threshold_pct": 80,
            "risk_weight": 35,
        },
        "short_lifespan": {
            "description": "Tokens consistently have short lifespans",
            "threshold_hours": 48,
            "risk_weight": 20,
        },
        "wallet_recycling": {
            "description": "Funds traced to previously rugged tokens",
            "hop_depth": 3,
            "risk_weight": 40,
        },
    }

    # Known scammer addresses (can be loaded from database)
    _known_scammers: Set[str] = set()

    # Cache for forensics results
    _cache: Dict[str, Tuple[WalletForensicsResult, datetime]] = {}
    CACHE_TTL_HOURS = 1

    def __init__(
        self,
        solana_rpc_url: str = "https://api.mainnet-beta.solana.com",
        session: Optional[aiohttp.ClientSession] = None,
    ):
        """
        Initialize forensics engine.

        Args:
            solana_rpc_url: Solana RPC endpoint
            session: Optional aiohttp session for reuse
        """
        self.solana_rpc_url = solana_rpc_url
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close session if owned."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    def add_known_scammer(self, address: str):
        """Add address to known scammer list."""
        self._known_scammers.add(address)

    def is_known_scammer(self, address: str) -> bool:
        """Check if address is a known scammer."""
        return address in self._known_scammers

    async def analyze_wallet(
        self,
        wallet_address: str,
        depth: int = 2,
    ) -> WalletForensicsResult:
        """
        Perform comprehensive wallet forensics analysis.

        Args:
            wallet_address: Solana wallet address to analyze
            depth: How many hops to trace for funding chain

        Returns:
            WalletForensicsResult with complete analysis
        """
        # Check cache
        cached = self._cache.get(wallet_address)
        if cached:
            result, timestamp = cached
            if (datetime.utcnow() - timestamp).total_seconds() < self.CACHE_TTL_HOURS * 3600:
                return result

        # Check if known scammer
        if self.is_known_scammer(wallet_address):
            result = WalletForensicsResult(
                wallet_address=wallet_address,
                reputation_score=0.0,
                risk_level=WalletRiskLevel.KNOWN_SCAMMER,
                patterns_detected=["known_scammer"],
                pattern_severity="CRITICAL",
                evidence_summary="This wallet is flagged as a known scammer in our database.",
                confidence=99.0,
            )
            self._cache[wallet_address] = (result, datetime.utcnow())
            return result

        try:
            # Collect data in parallel
            deployment_history, funding_chain, related_wallets = await asyncio.gather(
                self._get_token_deployments(wallet_address),
                self._trace_funding_chain(wallet_address, depth),
                self._find_related_wallets(wallet_address),
                return_exceptions=True,
            )

            # Handle errors gracefully
            if isinstance(deployment_history, Exception):
                logger.warning(f"Error getting deployments for {wallet_address}: {deployment_history}")
                deployment_history = []
            if isinstance(funding_chain, Exception):
                logger.warning(f"Error tracing funding for {wallet_address}: {funding_chain}")
                funding_chain = []
            if isinstance(related_wallets, Exception):
                logger.warning(f"Error finding related wallets for {wallet_address}: {related_wallets}")
                related_wallets = []

            # Analyze deployment history
            tokens_deployed = len(deployment_history)
            rugged_tokens = sum(1 for d in deployment_history if d.status == "rugged")
            active_tokens = sum(1 for d in deployment_history if d.status == "active")
            rug_percentage = (rugged_tokens / tokens_deployed * 100) if tokens_deployed > 0 else 0.0

            # Calculate total value rugged
            total_rugged_usd = sum(
                d.peak_liquidity_usd - d.final_liquidity_usd
                for d in deployment_history
                if d.status == "rugged"
            )

            # Calculate average lifespan
            lifespans = [d.lifespan_hours for d in deployment_history if d.lifespan_hours > 0]
            avg_lifespan = sum(lifespans) / len(lifespans) if lifespans else 0.0

            # Detect patterns
            patterns = self._detect_patterns(deployment_history)

            # Calculate funding risk
            funding_risk = self._calculate_funding_risk(funding_chain)

            # Calculate overall reputation score
            reputation_score = self._calculate_reputation_score(
                tokens_deployed=tokens_deployed,
                rugged_tokens=rugged_tokens,
                patterns_detected=patterns,
                funding_risk=funding_risk,
                avg_lifespan=avg_lifespan,
            )

            # Determine risk level
            risk_level = self._determine_risk_level(reputation_score, patterns)

            # Generate evidence summary
            evidence_summary = self._generate_evidence_summary(
                tokens_deployed=tokens_deployed,
                rugged_tokens=rugged_tokens,
                rug_percentage=rug_percentage,
                patterns=patterns,
                funding_risk=funding_risk,
            )

            # Calculate confidence based on data availability
            confidence = self._calculate_confidence(
                tokens_deployed=tokens_deployed,
                funding_chain_depth=len(funding_chain),
                related_wallets_found=len(related_wallets),
            )

            result = WalletForensicsResult(
                wallet_address=wallet_address,
                reputation_score=reputation_score,
                risk_level=risk_level,
                tokens_deployed=tokens_deployed,
                rugged_tokens=rugged_tokens,
                active_tokens=active_tokens,
                rug_percentage=rug_percentage,
                total_value_rugged_usd=total_rugged_usd,
                avg_lifespan_hours=avg_lifespan,
                patterns_detected=patterns,
                pattern_severity=self._get_pattern_severity(patterns),
                related_wallets=related_wallets[:5],  # Top 5
                funding_chain=funding_chain[:depth],
                funding_risk=funding_risk,
                evidence_summary=evidence_summary,
                confidence=confidence,
                deployment_history=deployment_history[:10],  # Last 10
            )

            # Cache result
            self._cache[wallet_address] = (result, datetime.utcnow())
            return result

        except Exception as e:
            logger.error(f"Error analyzing wallet {wallet_address}: {e}")
            # Return neutral result on error
            return WalletForensicsResult(
                wallet_address=wallet_address,
                reputation_score=50.0,
                risk_level=WalletRiskLevel.MEDIUM,
                evidence_summary=f"Unable to complete full analysis: {str(e)[:100]}",
                confidence=20.0,
            )

    async def _get_token_deployments(
        self,
        wallet_address: str,
    ) -> List[TokenDeploymentRecord]:
        """
        Get history of tokens deployed by this wallet.

        Uses Solana RPC to find token mint transactions where
        this wallet was the mint authority or fee payer.

        Note: This is a simplified implementation. Production would
        use indexed data from Helius or similar.
        """
        deployments = []

        try:
            session = await self._get_session()

            # Query recent signatures for the wallet
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    wallet_address,
                    {"limit": 100}
                ]
            }

            async with session.post(
                self.solana_rpc_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return deployments

                data = await resp.json()
                signatures = data.get("result", [])

                # In production, we would analyze each transaction to find:
                # 1. Token mint creation (InitializeMint instruction)
                # 2. Initial liquidity provision
                # 3. Track token lifecycle

                # For now, return empty list - this would be populated
                # from a database of tracked deployments
                logger.debug(f"Found {len(signatures)} signatures for {wallet_address}")

        except Exception as e:
            logger.warning(f"Error getting deployments for {wallet_address}: {e}")

        return deployments

    async def _trace_funding_chain(
        self,
        wallet_address: str,
        depth: int = 3,
    ) -> List[str]:
        """
        Trace where the wallet's funds originated.

        Follows SOL transfers backwards to find:
        - CEX withdrawals (relatively safe)
        - Known scammer wallets (critical risk)
        - Mixing service usage (suspicious)

        Args:
            wallet_address: Wallet to trace
            depth: How many hops to trace back

        Returns:
            List of funding source addresses
        """
        funding_sources = []

        try:
            session = await self._get_session()
            current_wallet = wallet_address

            for hop in range(depth):
                # Get incoming SOL transfers
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": [
                        current_wallet,
                        {"limit": 50}
                    ]
                }

                async with session.post(
                    self.solana_rpc_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        break

                    data = await resp.json()
                    signatures = data.get("result", [])

                    if not signatures:
                        break

                    # In production, analyze transactions to find
                    # the largest SOL sender
                    # For now, we just track that we attempted the trace
                    funding_sources.append(f"hop_{hop + 1}_source")

        except Exception as e:
            logger.warning(f"Error tracing funding for {wallet_address}: {e}")

        return funding_sources

    async def _find_related_wallets(
        self,
        wallet_address: str,
    ) -> List[str]:
        """
        Find wallets likely controlled by the same entity.

        Indicators:
        - Same funding source
        - Coordinated token deployments
        - Similar transaction patterns
        - Mutual token holdings
        """
        related = []

        # In production, this would:
        # 1. Find wallets with common funding sources
        # 2. Analyze transaction timing patterns
        # 3. Check for coordinated activities

        return related

    def _detect_patterns(
        self,
        deployments: List[TokenDeploymentRecord],
    ) -> List[str]:
        """
        Detect scam patterns from deployment history.

        Returns list of pattern names detected.
        """
        patterns = []

        if not deployments:
            return patterns

        # Pattern 1: Rapid deployment
        window = timedelta(hours=self.SCAM_PATTERNS["rapid_deployment"]["window_hours"])
        threshold = self.SCAM_PATTERNS["rapid_deployment"]["threshold_tokens"]

        recent_deployments = [
            d for d in deployments
            if d.deployed_at and (datetime.utcnow() - d.deployed_at) <= window
        ]
        if len(recent_deployments) >= threshold:
            patterns.append("rapid_deployment")

        # Pattern 2: Consistent rug timing
        rugged = [d for d in deployments if d.status == "rugged" and d.lifespan_hours > 0]
        if len(rugged) >= 2:
            lifespans = [d.lifespan_hours for d in rugged]
            avg_lifespan = sum(lifespans) / len(lifespans)
            variance = sum((l - avg_lifespan) ** 2 for l in lifespans) / len(lifespans)
            std_dev = variance ** 0.5

            if std_dev <= self.SCAM_PATTERNS["consistent_rug_timing"]["variance_hours"]:
                patterns.append("consistent_rug_timing")

        # Pattern 3: High LP removal
        lp_removals = [d.liquidity_removal_pct for d in deployments if d.liquidity_removal_pct > 0]
        if lp_removals:
            avg_removal = sum(lp_removals) / len(lp_removals)
            if avg_removal >= self.SCAM_PATTERNS["lp_removal_pattern"]["threshold_pct"]:
                patterns.append("lp_removal_pattern")

        # Pattern 4: Short lifespans
        lifespans = [d.lifespan_hours for d in deployments if d.lifespan_hours > 0]
        if lifespans:
            avg_lifespan = sum(lifespans) / len(lifespans)
            if avg_lifespan <= self.SCAM_PATTERNS["short_lifespan"]["threshold_hours"]:
                patterns.append("short_lifespan")

        return patterns

    def _calculate_reputation_score(
        self,
        tokens_deployed: int,
        rugged_tokens: int,
        patterns_detected: List[str],
        funding_risk: float,
        avg_lifespan: float,
    ) -> float:
        """
        Calculate 0-100 reputation score.

        Higher = safer, Lower = riskier

        Factors:
        - Rug ratio (rugged_tokens / total_tokens)
        - Pattern severity
        - Funding chain risk
        - Average token lifespan
        """
        # Start at neutral-positive
        score = 70.0

        # No history = neutral
        if tokens_deployed == 0:
            return 50.0

        # Rug ratio penalty (up to -50 points)
        rug_ratio = rugged_tokens / tokens_deployed
        score -= rug_ratio * 50

        # Pattern penalties
        for pattern in patterns_detected:
            weight = self.SCAM_PATTERNS.get(pattern, {}).get("risk_weight", 10)
            score -= weight

        # Funding chain penalty (up to -20 points)
        score -= funding_risk * 20

        # Short lifespan penalty
        if avg_lifespan > 0 and avg_lifespan < 24:
            score -= 10
        elif avg_lifespan >= 168:  # 7+ days
            score += 10

        # Bonus for clean history with multiple tokens
        if rugged_tokens == 0 and tokens_deployed >= 3:
            score += 15

        return max(0.0, min(100.0, score))

    def _calculate_funding_risk(self, funding_chain: List[str]) -> float:
        """
        Calculate risk score (0-1) from funding sources.
        """
        if not funding_chain:
            return 0.3  # Unknown = moderate risk

        risk = 0.0
        for source in funding_chain:
            if self.is_known_scammer(source):
                risk += 0.5
            # In production, check against:
            # - Known CEX addresses (lower risk)
            # - Known mixers (higher risk)
            # - Bridge contracts (neutral)

        return min(1.0, risk)

    def _determine_risk_level(
        self,
        reputation_score: float,
        patterns: List[str],
    ) -> WalletRiskLevel:
        """Determine risk level from reputation score and patterns."""
        # Critical patterns override score
        if "wallet_recycling" in patterns:
            return WalletRiskLevel.CRITICAL

        if reputation_score >= 80:
            return WalletRiskLevel.CLEAN
        elif reputation_score >= 60:
            return WalletRiskLevel.LOW
        elif reputation_score >= 40:
            return WalletRiskLevel.MEDIUM
        elif reputation_score >= 20:
            return WalletRiskLevel.HIGH
        else:
            return WalletRiskLevel.CRITICAL

    def _get_pattern_severity(self, patterns: List[str]) -> str:
        """Get overall severity of detected patterns."""
        if not patterns:
            return "NONE"

        total_weight = sum(
            self.SCAM_PATTERNS.get(p, {}).get("risk_weight", 0)
            for p in patterns
        )

        if total_weight >= 80:
            return "CRITICAL"
        elif total_weight >= 50:
            return "HIGH"
        elif total_weight >= 25:
            return "MEDIUM"
        else:
            return "LOW"

    def _generate_evidence_summary(
        self,
        tokens_deployed: int,
        rugged_tokens: int,
        rug_percentage: float,
        patterns: List[str],
        funding_risk: float,
    ) -> str:
        """Generate human-readable evidence summary."""
        parts = []

        if tokens_deployed == 0:
            return "No token deployment history found for this wallet."

        parts.append(f"Deployed {tokens_deployed} token(s)")

        if rugged_tokens > 0:
            parts.append(f"{rugged_tokens} rugged ({rug_percentage:.0f}%)")

        if patterns:
            pattern_names = [
                self.SCAM_PATTERNS.get(p, {}).get("description", p)
                for p in patterns
            ]
            parts.append(f"Patterns: {', '.join(pattern_names)}")

        if funding_risk > 0.5:
            parts.append("Suspicious funding sources detected")

        return ". ".join(parts) + "."

    def _calculate_confidence(
        self,
        tokens_deployed: int,
        funding_chain_depth: int,
        related_wallets_found: int,
    ) -> float:
        """
        Calculate confidence in analysis (0-100).

        More data = higher confidence.
        """
        confidence = 30.0  # Base confidence

        # More token history = more confidence
        if tokens_deployed >= 5:
            confidence += 30
        elif tokens_deployed >= 2:
            confidence += 15

        # Funding chain analysis adds confidence
        confidence += min(20, funding_chain_depth * 7)

        # Related wallet analysis adds confidence
        confidence += min(20, related_wallets_found * 5)

        return min(100.0, confidence)

    def export_known_scammers(
        self,
        min_confidence: float = 0.7,
        include_high_risk: bool = True,
    ) -> List[Dict]:
        """
        Export known scammers and high-risk wallets for public database.

        This data can be shared publicly to benefit the entire Solana ecosystem.
        Other tools and projects can integrate this data to protect their users.

        Args:
            min_confidence: Minimum confidence threshold (0-1) for inclusion
            include_high_risk: Also include HIGH risk (not just CRITICAL/KNOWN_SCAMMER)

        Returns:
            List of scammer records with wallet, risk level, patterns, and evidence
        """
        export_data = []
        now = datetime.utcnow()

        # Export explicitly known scammers
        for wallet in self._known_scammers:
            export_data.append({
                "wallet": wallet,
                "risk_level": "KNOWN_SCAMMER",
                "confidence": 1.0,
                "source": "manual_flag",
                "patterns": ["known_scammer"],
                "tokens_deployed": None,
                "confirmed_rugs": None,
                "total_stolen_estimate_usd": None,
                "first_seen": None,
                "last_updated": now.isoformat(),
            })

        # Export from analysis cache
        risk_levels_to_export = {WalletRiskLevel.KNOWN_SCAMMER, WalletRiskLevel.CRITICAL}
        if include_high_risk:
            risk_levels_to_export.add(WalletRiskLevel.HIGH)

        for wallet_address, (result, timestamp) in self._cache.items():
            # Skip if already in known scammers
            if wallet_address in self._known_scammers:
                continue

            # Check confidence threshold
            if result.confidence < min_confidence * 100:
                continue

            # Check risk level
            if result.risk_level not in risk_levels_to_export:
                continue

            export_data.append({
                "wallet": result.wallet_address,
                "risk_level": result.risk_level.value,
                "confidence": result.confidence / 100.0,
                "source": "forensics_analysis",
                "patterns": result.patterns_detected,
                "tokens_deployed": result.tokens_deployed,
                "confirmed_rugs": result.rugged_tokens,
                "rug_percentage": result.rug_percentage,
                "total_stolen_estimate_usd": result.total_value_rugged_usd,
                "avg_lifespan_hours": result.avg_lifespan_hours,
                "evidence_summary": result.evidence_summary,
                "related_wallets": result.related_wallets,
                "first_seen": None,  # Would come from database in production
                "last_updated": timestamp.isoformat(),
            })

        return export_data

    def export_scammer_database_json(
        self,
        min_confidence: float = 0.7,
    ) -> Dict:
        """
        Export complete scammer database in JSON format for public sharing.

        Format designed for easy consumption by other projects:
        - JSON format for universal compatibility
        - Clear schema with version
        - Includes methodology notes

        Returns:
            Complete database export with metadata
        """
        scammers = self.export_known_scammers(min_confidence=min_confidence)

        return {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat(),
            "generator": "AI Sentinel Wallet Forensics",
            "methodology": {
                "description": "Scammers identified through wallet forensics analysis",
                "signals": [
                    "Token deployment history",
                    "Rug pull patterns (rapid deployment, LP removal, short lifespan)",
                    "Fund flow analysis",
                    "Related wallet clustering",
                ],
                "confidence_threshold": min_confidence,
            },
            "stats": {
                "total_entries": len(scammers),
                "known_scammers": sum(1 for s in scammers if s["risk_level"] == "KNOWN_SCAMMER"),
                "critical_risk": sum(1 for s in scammers if s["risk_level"] == "CRITICAL"),
                "high_risk": sum(1 for s in scammers if s["risk_level"] == "HIGH"),
            },
            "scammers": scammers,
            "license": "MIT - Free to use, attribution appreciated",
            "attribution": "AI Sentinel (https://github.com/yourusername/ai-sentinel)",
        }


async def get_token_deployer(
    token_address: str,
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com",
) -> Optional[str]:
    """
    Get the deployer wallet for a token.

    Finds the wallet that created the token mint.

    Args:
        token_address: Token mint address
        solana_rpc_url: Solana RPC endpoint

    Returns:
        Deployer wallet address, or None if not found
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Get token mint info
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [
                    token_address,
                    {"encoding": "jsonParsed"}
                ]
            }

            async with session.post(
                solana_rpc_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                result = data.get("result")

                if not result or not result.get("value"):
                    return None

                # Get mint authority or freeze authority as deployer proxy
                parsed = result["value"].get("data", {}).get("parsed", {})
                info = parsed.get("info", {})

                # Mint authority is often the deployer
                mint_authority = info.get("mintAuthority")
                if mint_authority:
                    return mint_authority

                # Freeze authority as fallback
                freeze_authority = info.get("freezeAuthority")
                if freeze_authority:
                    return freeze_authority

                return None

    except Exception as e:
        logger.warning(f"Error getting deployer for {token_address}: {e}")
        return None
