"""
Core data models for Solana token analysis.

This module contains all the data classes and enums used throughout the application
for representing Solana token information, analysis results, and risk assessments.

NOTE: All models are designed exclusively for Solana blockchain tokens.
Fields like mint_authority and freeze_authority are Solana-specific concepts.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any


class RiskLevel(Enum):
    """Risk level classification for tokens"""
    SAFE = ("🟢", "SAFE")
    LOW = ("🟡", "LOW RISK")
    MEDIUM = ("🟠", "MEDIUM")
    HIGH = ("🔴", "HIGH RISK")
    CRITICAL = ("⛔", "CRITICAL")

    @property
    def emoji(self) -> str:
        """Get the emoji representation"""
        return self.value[0]

    @property
    def label(self) -> str:
        """Get the text label"""
        return self.value[1]


@dataclass
class TokenInfo:
    """
    Complete token information and analysis data.

    This dataclass holds all information about a token including:
    - Basic token metadata (name, symbol, supply)
    - On-chain security data (authorities, holder distribution)
    - Market data (price, volume, liquidity)
    - Social media presence
    - AI analysis results from multiple providers
    - Risk assessment scores
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # BASIC TOKEN INFO
    # ═══════════════════════════════════════════════════════════════════════════

    address: str
    name: str = "Unknown"
    symbol: str = "???"
    decimals: int = 9
    supply: float = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # ON-CHAIN SECURITY
    # ═══════════════════════════════════════════════════════════════════════════

    mint_authority_enabled: bool = True
    freeze_authority_enabled: bool = True

    # ═══════════════════════════════════════════════════════════════════════════
    # HOLDER ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════

    top_holders: List[Dict] = field(default_factory=list)
    holder_concentration: float = 0.0

    # Enhanced holder metrics
    top_holder_pct: float = 0.0  # Percentage held by top wallet
    dev_wallet_risk: bool = False  # Suspected dev wallet
    suspicious_wallets: int = 0  # Number of suspicious wallets
    holder_flags: List[str] = field(default_factory=list)  # Wallet flags

    # ═══════════════════════════════════════════════════════════════════════════
    # MARKET DATA
    # ═══════════════════════════════════════════════════════════════════════════

    price_usd: float = 0.0
    market_cap: float = 0.0
    fdv: float = 0.0
    volume_24h: float = 0.0
    volume_1h: float = 0.0
    price_change_24h: float = 0.0
    price_change_6h: float = 0.0
    price_change_1h: float = 0.0
    price_change_5m: float = 0.0

    # ═══════════════════════════════════════════════════════════════════════════
    # LIQUIDITY
    # ═══════════════════════════════════════════════════════════════════════════

    liquidity_usd: float = 0.0
    liquidity_locked: bool = False
    lp_lock_percent: float = 0.0

    # ═══════════════════════════════════════════════════════════════════════════
    # TRADING ACTIVITY
    # ═══════════════════════════════════════════════════════════════════════════

    txns_24h: int = 0
    buys_24h: int = 0
    sells_24h: int = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # SOCIAL MEDIA PRESENCE
    # ═══════════════════════════════════════════════════════════════════════════

    has_twitter: bool = False
    has_website: bool = False
    has_telegram: bool = False
    twitter_url: Optional[str] = None
    website_url: Optional[str] = None
    telegram_url: Optional[str] = None
    socials_count: int = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # METADATA
    # ═══════════════════════════════════════════════════════════════════════════

    logo_url: Optional[str] = None

    # ═══════════════════════════════════════════════════════════════════════════
    # POOL INFORMATION
    # ═══════════════════════════════════════════════════════════════════════════

    pair_address: Optional[str] = None
    dex_name: str = "Unknown"
    age_hours: float = 0.0

    # ═══════════════════════════════════════════════════════════════════════════
    # RUGCHECK DATA
    # ═══════════════════════════════════════════════════════════════════════════

    rugcheck_score: int = 0
    rugcheck_risks: List[str] = field(default_factory=list)

    # ═══════════════════════════════════════════════════════════════════════════
    # RISK ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════

    risk_score: int = 0
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_factors: List[str] = field(default_factory=list)
    positive_factors: List[str] = field(default_factory=list)

    # ═══════════════════════════════════════════════════════════════════════════
    # AI ANALYSIS (PRIMARY - OpenAI/OpenRouter)
    # ═══════════════════════════════════════════════════════════════════════════

    ai_summary: str = ""
    ai_recommendation: str = ""
    ai_risk_assessment: str = ""
    ai_narrative: str = ""
    ai_website_type: str = "unknown"  # Token type for display (memecoin, DeFi, utility, etc.)

    # Enhanced AI metrics
    ai_score: int = 50  # AI's independent score 0-100
    ai_confidence: int = 50  # AI's confidence in analysis
    ai_rug_probability: int = 50  # Rug pull probability %
    ai_verdict: str = "CAUTION"  # SAFE/CAUTION/RISKY/DANGEROUS/SCAM
    ai_red_flags: List[str] = field(default_factory=list)
    ai_green_flags: List[str] = field(default_factory=list)
    ai_code_audit: str = ""
    ai_whale_risk: str = ""
    ai_sentiment: str = ""
    ai_trading: str = ""

    # ═══════════════════════════════════════════════════════════════════════════
    # WEBSITE ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════

    # Core website data
    website_content: str = ""
    website_title: str = ""
    website_description: str = ""
    website_quality: int = 0  # 0-100
    website_is_legitimate: bool = False
    website_red_flags: List[str] = field(default_factory=list)
    website_load_time: float = 0.0

    # Trust signals
    website_has_privacy_policy: bool = False
    website_has_terms: bool = False
    website_has_copyright: bool = False
    website_copyright_year: Optional[int] = None
    website_has_contact: bool = False
    website_contact_email: Optional[str] = None
    website_has_company_name: bool = False
    website_company_name: Optional[str] = None
    website_has_physical_address: bool = False

    # Token integration signals
    website_has_contract_displayed: bool = False
    website_contract_displayed: Optional[str] = None
    website_has_tokenomics_numbers: bool = False
    website_tokenomics_details: List[str] = field(default_factory=list)
    website_has_buy_button: bool = False
    website_buy_links: List[str] = field(default_factory=list)
    website_has_audit: bool = False
    website_audit_provider: Optional[str] = None

    # Technical quality signals
    website_has_mobile_viewport: bool = False
    website_has_favicon: bool = False
    website_has_analytics: bool = False
    website_uses_modern_framework: bool = False
    website_framework_detected: Optional[str] = None
    website_is_spa: bool = False
    website_has_custom_domain: bool = True

    # Social presence on website
    website_social_links: Dict[str, str] = field(default_factory=dict)
    website_has_discord: bool = False
    website_has_medium: bool = False
    website_has_github: bool = False

    # Section presence
    website_has_whitepaper: bool = False
    website_has_roadmap: bool = False
    website_has_team: bool = False
    website_has_tokenomics: bool = False

    # AI website assessment
    website_ai_quality: str = ""  # professional|legitimate|neutral|suspicious|scam_likely
    website_ai_concerns: List[str] = field(default_factory=list)

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA AVAILABILITY FLAGS
    # ═══════════════════════════════════════════════════════════════════════════

    # Flag to track if AI analysis succeeded
    ai_available: bool = False  # OpenAI/OpenRouter analysis succeeded

    # ═══════════════════════════════════════════════════════════════════════════
    # DEPLOYER FORENSICS (Developer Wallet Analysis)
    # ═══════════════════════════════════════════════════════════════════════════

    deployer_address: Optional[str] = None  # Wallet that deployed the token
    deployer_reputation_score: float = 50.0  # 0-100 (higher = safer)
    deployer_risk_level: str = "UNKNOWN"  # CLEAN, LOW, MEDIUM, HIGH, CRITICAL, KNOWN_SCAMMER
    deployer_tokens_deployed: int = 0  # Historical token count
    deployer_rugged_tokens: int = 0  # Historical rug count
    deployer_rug_percentage: float = 0.0  # % of tokens that were rugs
    deployer_patterns_detected: List[str] = field(default_factory=list)  # Detected scam patterns
    deployer_is_known_scammer: bool = False  # Flagged as known scammer
    deployer_evidence_summary: str = ""  # Human-readable evidence
    deployer_forensics_available: bool = False  # Flag if analysis succeeded

    # ═══════════════════════════════════════════════════════════════════════════
    # BEHAVIORAL ANOMALY DETECTION (Predictive Rug Detection)
    # ═══════════════════════════════════════════════════════════════════════════

    anomaly_score: float = 0.0  # 0-100 (higher = more anomalous)
    anomaly_rug_probability: float = 15.0  # 0-100 predicted rug likelihood
    anomaly_time_to_rug: Optional[str] = None  # "imminent", "hours", "days", None
    anomaly_severity: str = "NORMAL"  # NORMAL, ELEVATED, HIGH, CRITICAL
    anomalies_detected: List[str] = field(default_factory=list)  # Detected anomaly types
    anomaly_recommendation: str = ""  # Action recommendation
    anomaly_data_quality: float = 0.0  # 0-100 data quality score
    anomaly_confidence: float = 50.0  # 0-100 confidence in prediction
    anomaly_available: bool = False  # Flag if analysis succeeded

    # ═══════════════════════════════════════════════════════════════════════════
    # HONEYPOT DETECTION (Sell Simulation)
    # ═══════════════════════════════════════════════════════════════════════════

    honeypot_status: str = "unknown"  # safe, high_tax, extreme_tax, honeypot, unable_to_verify, error
    honeypot_is_honeypot: bool = False  # Confirmed honeypot flag
    honeypot_confidence: float = 0.0  # 0-1 confidence in detection
    honeypot_sell_tax_percent: Optional[float] = None  # Detected sell tax %
    honeypot_route_available: bool = False  # Whether Jupiter has a route
    honeypot_route_dex: Optional[str] = None  # Primary DEX for selling
    honeypot_price_impact: float = 0.0  # Price impact on simulated sell
    honeypot_warnings: List[str] = field(default_factory=list)  # Warning messages
    honeypot_explanation: str = ""  # Human-readable explanation
    honeypot_checked: bool = False  # Flag if honeypot check was performed


@dataclass
class AnalysisResult:
    """
    Complete analysis result with all scoring metrics.

    This dataclass aggregates all analysis scores and provides
    a final recommendation for the token.
    """

    # Core token data
    token: TokenInfo

    # ═══════════════════════════════════════════════════════════════════════════
    # SCORING METRICS
    # ═══════════════════════════════════════════════════════════════════════════

    safety_score: int  # On-chain security (authorities, LP lock)
    liquidity_score: int  # Liquidity depth and quality
    distribution_score: int  # Token distribution fairness
    activity_score: int  # Trading activity and volume
    social_score: int  # Social media presence

    # Overall metrics
    overall_score: int  # Weighted average of all scores
    grade: str  # Letter grade (A+ to F)
    recommendation: str  # BUY/HOLD/AVOID/etc

    # NEW: Advanced analytics scoring (with defaults, must come after required fields)
    deployer_reputation_score: int = 50  # Deployer wallet reputation (0-100)
    behavioral_anomaly_score: int = 100  # Behavioral anomaly score (0-100, lower = more anomalous)
    honeypot_score: int = 70  # Honeypot detection score (0-100, 0 = confirmed honeypot)

    # ═══════════════════════════════════════════════════════════════════════════
    # AI ANALYSIS SUMMARIES
    # ═══════════════════════════════════════════════════════════════════════════

    ai_analysis: str = ""  # Primary AI analysis (OpenAI/OpenRouter)
