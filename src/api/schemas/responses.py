"""
API Response schemas for the Ilyon AI Web API.

Pydantic models that define the structure of all API responses.
These are designed to match the frontend TypeScript interfaces.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class VerdictType(str, Enum):
    """AI verdict classification"""
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    RISKY = "RISKY"
    DANGEROUS = "DANGEROUS"
    SCAM = "SCAM"


class GradeType(str, Enum):
    """Token grade classification"""
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


# ═══════════════════════════════════════════════════════════════════════════
# TOKEN ANALYSIS RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class TokenBasicInfo(BaseModel):
    """Basic token information"""
    address: str
    name: str
    symbol: str
    decimals: int = 9
    logo_url: Optional[str] = None
    chain: str = "solana"
    chain_id: Optional[int] = None
    explorer_url: Optional[str] = None


class ScoresResponse(BaseModel):
    """All scoring metrics"""
    overall: int = Field(..., ge=0, le=100)
    grade: str
    safety: int = Field(..., ge=0, le=100)
    liquidity: int = Field(..., ge=0, le=100)
    distribution: int = Field(..., ge=0, le=100)
    social: int = Field(..., ge=0, le=100)
    activity: int = Field(..., ge=0, le=100)
    honeypot: int = Field(default=70, ge=0, le=100)
    deployer: int = Field(default=50, ge=0, le=100)
    anomaly: int = Field(default=100, ge=0, le=100)


class MarketDataResponse(BaseModel):
    """Market and trading data"""
    price_usd: float
    market_cap: float
    fdv: float
    liquidity_usd: float
    volume_24h: float
    volume_1h: float
    price_change_24h: float
    price_change_6h: float
    price_change_1h: float
    price_change_5m: float
    buys_24h: int
    sells_24h: int
    txns_24h: int
    age_hours: float
    dex_name: str
    pair_address: Optional[str] = None


class SecurityResponse(BaseModel):
    """Security and on-chain checks"""
    mint_authority_enabled: bool
    freeze_authority_enabled: bool
    liquidity_locked: Optional[bool] = None
    lp_lock_percent: Optional[float] = None
    liquidity_lock_status: str = "unknown"
    liquidity_lock_source: Optional[str] = None
    liquidity_lock_note: Optional[str] = None
    honeypot_status: str
    honeypot_is_honeypot: bool
    honeypot_sell_tax_percent: Optional[float] = None
    honeypot_explanation: str
    honeypot_warnings: List[str] = []
    # Universal cross-chain security fields
    can_mint: bool = True
    can_blacklist: bool = False
    can_pause: bool = False
    is_upgradeable: bool = False
    is_renounced: bool = False
    is_proxy_contract: Optional[bool] = None
    is_verified: Optional[bool] = None
    buy_tax: Optional[float] = None
    sell_tax: Optional[float] = None
    transfer_pausable: Optional[bool] = None
    is_open_source: Optional[bool] = None


class HolderAnalysisResponse(BaseModel):
    """Holder distribution analysis"""
    top_holder_pct: float
    holder_concentration: float
    suspicious_wallets: int
    dev_wallet_risk: bool
    holder_flags: List[str] = []
    top_holders: List[Dict[str, Any]] = []


class AIAnalysisResponse(BaseModel):
    """AI analysis results"""
    available: bool
    verdict: str
    score: int
    confidence: int
    rug_probability: int
    summary: str
    recommendation: str
    red_flags: List[str] = []
    green_flags: List[str] = []
    code_audit: str = ""
    whale_risk: str = ""
    sentiment: str = ""
    trading: str = ""
    narrative: str = ""
    grok: Optional[Dict[str, Any]] = None  # Structured narrative data


class SocialsResponse(BaseModel):
    """Social media presence"""
    has_twitter: bool
    has_website: bool
    has_telegram: bool
    twitter_url: Optional[str] = None
    website_url: Optional[str] = None
    telegram_url: Optional[str] = None
    socials_count: int


class WebsiteAnalysisResponse(BaseModel):
    """Website quality analysis"""
    quality: int = Field(default=0, ge=0, le=100)
    is_legitimate: bool
    has_privacy_policy: bool
    has_terms: bool
    has_copyright: bool
    has_contact: bool
    has_tokenomics: bool
    has_roadmap: bool
    has_team: bool
    has_whitepaper: bool
    has_audit: bool
    audit_provider: Optional[str] = None
    red_flags: List[str] = []
    ai_quality: str = ""
    ai_concerns: List[str] = []


class DeployerForensicsResponse(BaseModel):
    """Deployer wallet forensics"""
    available: bool
    address: Optional[str] = None
    reputation_score: float
    risk_level: str
    tokens_deployed: int
    rugged_tokens: int
    rug_percentage: float
    is_known_scammer: bool
    patterns_detected: List[str] = []
    evidence_summary: str = ""


class AnomalyDetectionResponse(BaseModel):
    """Behavioral anomaly detection"""
    available: bool
    score: float
    rug_probability: float
    time_to_rug: Optional[str] = None
    severity: str
    anomalies_detected: List[str] = []
    recommendation: str = ""
    confidence: float


class AnalysisResponse(BaseModel):
    """Complete token analysis response"""
    token: TokenBasicInfo
    scores: ScoresResponse
    market: MarketDataResponse
    security: SecurityResponse
    holders: HolderAnalysisResponse
    ai: AIAnalysisResponse
    socials: SocialsResponse
    website: WebsiteAnalysisResponse
    deployer: DeployerForensicsResponse
    anomaly: AnomalyDetectionResponse
    recommendation: str
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    analysis_mode: str = "standard"
    cached: bool = False
    chain: str = "solana"

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ═══════════════════════════════════════════════════════════════════════════
# TRENDING TOKENS RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class TrendingTokenResponse(BaseModel):
    """Single trending token"""
    address: str
    chain: str = "solana"
    name: str
    symbol: str
    logo_url: Optional[str] = None
    price_usd: float
    price_change_24h: float
    price_change_1h: float
    volume_24h: float
    liquidity_usd: float
    market_cap: float
    age_hours: float
    dex_name: str
    pair_address: Optional[str] = None
    txns_1h: Optional[int] = None  # Total transactions in last 1 hour


class TrendingResponse(BaseModel):
    """Trending tokens list response"""
    tokens: List[TrendingTokenResponse]
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    category: str = "trending"  # trending, gainers, losers, new
    filter_chain: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ═══════════════════════════════════════════════════════════════════════════
# PORTFOLIO RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class PortfolioTokenResponse(BaseModel):
    """Token in portfolio"""
    address: str
    name: str
    symbol: str
    chain: Optional[str] = Field(default="solana", description="Blockchain network")
    logo_url: Optional[str] = None
    balance: float
    balance_usd: float
    price_usd: float
    price_change_24h: float
    safety_score: Optional[int] = None
    risk_level: str = "UNKNOWN"


class PortfolioResponse(BaseModel):
    """Portfolio overview response"""
    wallet_address: str
    total_value_usd: float
    total_pnl_usd: float
    total_pnl_percent: float
    tokens: List[PortfolioTokenResponse]
    health_score: int = Field(default=50, ge=0, le=100)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TrackedWalletResponse(BaseModel):
    """Tracked wallet info"""
    address: str
    label: Optional[str] = None
    added_at: datetime
    last_synced: Optional[datetime] = None
    token_count: int = 0
    total_value_usd: float = 0


class TrackedWalletsResponse(BaseModel):
    """List of tracked wallets"""
    wallets: List[TrackedWalletResponse]


# ═══════════════════════════════════════════════════════════════════════════
# WHALE TRACKER RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class WhaleTransactionResponse(BaseModel):
    """Single whale transaction"""
    signature: str
    wallet_address: str
    wallet_label: Optional[str] = None
    token_address: str
    token_symbol: str
    token_name: str
    type: str  # "buy" or "sell"
    amount_tokens: float
    amount_usd: float
    price_usd: float
    timestamp: datetime
    dex_name: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WhaleActivityResponse(BaseModel):
    """Whale activity feed response"""
    transactions: List[WhaleTransactionResponse]
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    filter_token: Optional[str] = None
    min_amount_usd: float = 10000

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WhaleProfileResponse(BaseModel):
    """Whale wallet profile"""
    address: str
    label: Optional[str] = None
    total_volume_usd: float
    transaction_count: int
    tokens_traded: int
    win_rate: Optional[float] = None
    avg_holding_time: Optional[str] = None
    recent_transactions: List[WhaleTransactionResponse] = []


# ═══════════════════════════════════════════════════════════════════════════
# ALERTS RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class AlertType(str, Enum):
    """Alert type classification"""
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    SCORE_BELOW = "score_below"
    WHALE_ACTIVITY = "whale_activity"
    HONEYPOT_DETECTED = "honeypot_detected"


class AlertResponse(BaseModel):
    """Single alert configuration"""
    id: str
    token_address: str
    token_symbol: str
    alert_type: AlertType
    threshold: float
    enabled: bool
    created_at: datetime
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AlertsListResponse(BaseModel):
    """List of user alerts"""
    alerts: List[AlertResponse]
    max_alerts: int = 10


# ═══════════════════════════════════════════════════════════════════════════
# AUTH RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class AuthChallengeResponse(BaseModel):
    """Authentication challenge for wallet signing"""
    challenge: str
    expires_at: datetime
    message: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AuthVerifyResponse(BaseModel):
    """Authentication verification result"""
    success: bool
    wallet_address: str
    session_token: str
    expires_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserProfileResponse(BaseModel):
    """User profile information"""
    wallet_address: str
    created_at: datetime
    analyses_count: int
    tracked_wallets: int
    alerts_count: int
    premium_until: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ═══════════════════════════════════════════════════════════════════════════
# ERROR RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    code: str
    details: Optional[Dict[str, Any]] = None


class ValidationErrorResponse(BaseModel):
    """Validation error response"""
    error: str = "Validation error"
    code: str = "VALIDATION_ERROR"
    fields: Dict[str, List[str]] = {}


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET MESSAGES
# ═══════════════════════════════════════════════════════════════════════════

class AnalysisProgressMessage(BaseModel):
    """WebSocket message for analysis progress"""
    type: str = "analysis_progress"
    address: str
    stage: int  # 1-4
    stage_name: str
    progress: int  # 0-100
    message: str


class AnalysisCompleteMessage(BaseModel):
    """WebSocket message for analysis completion"""
    type: str = "analysis_complete"
    address: str
    result: AnalysisResponse


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD STATS RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class VolumeDataPoint(BaseModel):
    """Single volume data point for chart - can be time or token symbol"""
    time: str  # Can be time label or token symbol
    volume: float


class RiskDistributionItem(BaseModel):
    """Risk distribution category"""
    name: str
    count: int
    color: str


class MarketDistributionItem(BaseModel):
    """Market category distribution"""
    name: str
    value: float
    color: str


class TopTokenVolume(BaseModel):
    """Token volume data for chart"""
    symbol: str
    volume: float
    address: str


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics response - all data from real token analysis"""
    # Main metrics (from tracked trending tokens)
    total_volume_24h: float  # Sum of 24h volume from tracked tokens
    volume_change_24h: float
    solana_tvl: float = 0  # Solana total value locked from DefiLlama
    sol_price: float = 0  # Current SOL price in USD
    sol_price_change_24h: float = 0  # SOL 24h price change %
    active_tokens: int  # Number of tokens being tracked (kept for compatibility)
    active_tokens_change: int
    safe_tokens_percent: float  # % of tracked tokens classified as safe
    safe_tokens_change: float
    scams_detected: int  # Kept for backward compatibility
    scams_change: int
    high_risk_tokens: int = 0  # Renamed from scams_detected - Risky + Scam tokens count

    # Liquidity metrics
    avg_liquidity: float  # Average liquidity of tracked tokens
    total_liquidity: float  # Total liquidity across tracked tokens

    # Chart data
    volume_chart: List[VolumeDataPoint]  # Top tokens by volume
    risk_distribution: List[RiskDistributionItem]
    market_distribution: List[MarketDistributionItem] = []  # Token categories
    top_tokens_by_volume: List[Dict[str, Any]] = []  # Detailed token volume data

    # Analysis stats
    tokens_analyzed_today: int
    total_tokens_analyzed: int

    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ═══════════════════════════════════════════════════════════════════════════
# CHAINS RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class ChainInfoResponse(BaseModel):
    """Single chain information"""
    chain: str
    chain_id: Optional[int] = None
    display_name: str
    native_currency: str
    explorer_url: str
    is_evm: bool
    block_time_seconds: float = 0
    logo: str = ""
    primary_dex: Optional[str] = None


class ChainsListResponse(BaseModel):
    """List of supported chains"""
    chains: List[ChainInfoResponse]
    total: int


# ═══════════════════════════════════════════════════════════════════════════
# CONTRACT SCANNER RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class VulnerabilityItem(BaseModel):
    """Single vulnerability finding"""
    severity: str  # critical / high / medium / low / info
    title: str
    description: str
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    recommendation: str = ""


class ContractScanResponse(BaseModel):
    """Contract security scan result"""
    address: str
    chain: str
    name: Optional[str] = None
    is_verified: bool = False
    compiler_version: Optional[str] = None
    license: Optional[str] = None
    is_proxy: bool = False
    proxy_implementation: Optional[str] = None
    overall_risk: str = "UNKNOWN"
    risk_score: int = 50
    # Vulnerability findings
    vulnerabilities: List[VulnerabilityItem] = []
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    # AI audit
    ai_audit_summary: str = ""
    ai_risk_verdict: str = "UNKNOWN"  # SAFE / LOW / MEDIUM / HIGH / CRITICAL
    ai_confidence: int = 50
    ai_verdict: Optional[str] = None
    key_findings: List[str] = []
    recommendations: List[str] = []
    # Similarity matching
    similar_to_scam: bool = False
    similarity_score: float = 0.0
    similar_contract_info: Optional[str] = None
    # Metadata
    scanned_at: datetime = Field(default_factory=datetime.utcnow)
    scan_duration_ms: int = 0

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════
# SHIELD / APPROVAL MANAGER RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class ApprovalItem(BaseModel):
    """Single token approval"""
    token_address: str
    token_symbol: Optional[str] = None
    token_name: Optional[str] = None
    token_logo: Optional[str] = None
    spender_address: str
    spender_name: Optional[str] = None  # Known protocol name if identified
    spender_is_verified: bool = False
    allowance: str  # "unlimited" or formatted amount
    allowance_usd: Optional[float] = None
    risk_score: int = 50  # 0-100 (higher = more risky)
    risk_level: str = "MEDIUM"  # LOW / MEDIUM / HIGH / CRITICAL
    risk_reasons: List[str] = []
    chain: str
    last_used: Optional[datetime] = None
    approved_at: Optional[datetime] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ShieldScanResponse(BaseModel):
    """Shield wallet scan result"""
    wallet: str
    wallet_address: str
    chains_scanned: List[str] = []
    chain_labels: Dict[str, str] = {}
    summary: Dict[str, int]
    approvals: List[ApprovalItem] = []
    recommendation: str = ""
    scanned_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class RevokePreparationResponse(BaseModel):
    """Unsigned revoke transaction data"""
    action: str
    description: str
    chain: str
    chain_id: Optional[int] = None
    unsigned_transaction: Dict[str, Any]
    warning: str


# ═══════════════════════════════════════════════════════════════════════════
# DEFI PROTOCOL ANALYSIS RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class PoolResponse(BaseModel):
    """Normalized liquidity pool response."""
    pool: str
    project: str
    symbol: str
    chain: str
    tvlUsd: float
    apy: float
    apyBase: Optional[float] = None
    apyReward: Optional[float] = None
    ilRisk: Optional[str] = None
    risk_score: int = 50
    risk_level: str = "LOW"
    risk_flags: List[str] = []


class PoolsListResponse(BaseModel):
    """List of normalized pools."""
    pools: List[PoolResponse]
    count: int
    filters: Dict[str, Any] = {}
    summary: Dict[str, Any] = {}
    data_source: str = "DefiLlama"


class YieldOpportunityResponse(PoolResponse):
    """Normalized yield opportunity response."""
    apy_tier: str = "stable"
    exposure_type: str = "crypto-crypto"
    sustainability_ratio: float = 0.0


class YieldsListResponse(BaseModel):
    """List of normalized yield opportunities."""
    yields: List[YieldOpportunityResponse]
    count: int
    filters: Dict[str, Any] = {}
    data_source: str = "DefiLlama"


class LendingRiskBreakdownResponse(BaseModel):
    risk_level: str = "LOW"
    risk_score: int = 0
    risk_factors: List[str] = []


class LendingMarketResponse(BaseModel):
    pool_id: str
    protocol: str
    protocol_display: str
    symbol: str
    chain: str
    tvlUsd: float
    apy_supply: float
    apy_borrow: float
    utilization_pct: float
    audit_status: str = "unknown"
    auditors: List[str] = []
    incident_note: Optional[str] = None
    market_risk: LendingRiskBreakdownResponse
    protocol_risk: Optional[LendingRiskBreakdownResponse] = None
    combined_risk_score: float = 0.0


class LendingMarketsResponse(BaseModel):
    markets: List[LendingMarketResponse]
    count: int
    filters: Dict[str, Optional[str]] = {}
    data_source: str = "DefiLlama"


class HealthFactorResponse(BaseModel):
    health_factor: float
    status: str
    message: str
    collateral_drop_to_liquidation_pct: Optional[float] = None
    liquidation_threshold: Optional[float] = None
    collateral_usd: Optional[float] = None
    debt_usd: Optional[float] = None


class DefiProtocolMatchResponse(BaseModel):
    name: str
    slug: str
    symbol: Optional[str] = None
    tvl: float = 0.0
    chains: List[str] = []
    category: Optional[str] = None
    audits: Optional[str] = None
    url: Optional[str] = None
    logo: Optional[str] = None
    best_opportunity_score: Optional[int] = None
    best_safety_score: Optional[int] = None


class OpportunityDimensionResponse(BaseModel):
    key: str
    label: str
    score: int
    weight: float
    summary: str


class DefiEvidenceItemResponse(BaseModel):
    key: str
    title: str
    summary: str
    type: str
    severity: str = "low"
    source: str = "internal"
    url: Optional[str] = None


class DefiScenarioItemResponse(BaseModel):
    key: str
    title: str
    impact: str
    severity: str
    trigger: str


class DefiConfidenceResponse(BaseModel):
    score: int
    label: str
    coverage_ratio: float
    source_count: int
    freshness_hours: Optional[float] = None
    partial_analysis: bool = False
    missing_critical_fields: List[str] = []
    notes: List[str] = []


class DefiScoreCapResponse(BaseModel):
    dimension: str
    cap: int
    reason: str


class DefiDependencyResponse(BaseModel):
    key: str
    name: str
    dependency_type: str
    risk_score: int
    confidence_score: int
    source: str
    freshness_hours: Optional[float] = None
    notes: str = ""


class DefiAssetProfileResponse(BaseModel):
    symbol: str
    role: str
    chain: str
    quality_score: int
    risk_level: str
    confidence_score: int
    source: str
    address: Optional[str] = None
    thesis: str = ""
    token_analysis: Optional[Dict[str, Any]] = None


class DefiMarketBriefResponse(BaseModel):
    available: bool
    headline: str
    summary: str
    market_regime: str
    best_area: str
    avoid_zone: str
    monitor_triggers: List[str] = []


class DefiProtocolAIAnalysisResponse(BaseModel):
    available: bool
    headline: str
    summary: str
    best_for: str
    main_risks: List[str] = []
    monitor_triggers: List[str] = []
    safer_alternative: str = ""


class DefiOpportunityAIAnalysisResponse(BaseModel):
    available: bool
    headline: str
    summary: str
    best_for: str
    why_it_exists: Optional[str] = None
    main_risks: List[str] = []
    monitor_triggers: List[str] = []
    safer_alternative: str = ""


class DefiOpportunityHistoryResponse(BaseModel):
    available: bool
    points: List[Dict[str, Any]] = []
    apy_change_pct: Optional[float] = None
    tvl_change_pct: Optional[float] = None
    apy_delta_7d: Optional[float] = None
    apy_delta_30d: Optional[float] = None
    tvl_delta_7d: Optional[float] = None
    tvl_delta_30d: Optional[float] = None
    apy_persistence_score: Optional[int] = None


class DefiOpportunitySummaryResponse(BaseModel):
    overall_score: Optional[int] = None
    quality_score: Optional[int] = None
    opportunity_score: int
    safety_score: int
    risk_burden_score: Optional[int] = None
    yield_durability_score: Optional[int] = None
    yield_quality_score: int
    exit_liquidity_score: Optional[int] = None
    exit_quality_score: int
    apr_efficiency_score: Optional[int] = None
    effective_apr: Optional[float] = None
    required_apr: Optional[float] = None
    return_potential_score: Optional[int] = None
    confidence_score: int
    risk_level: str
    strategy_fit: str
    headline: str
    thesis: str


class DefiProtocolSummaryResponse(BaseModel):
    tvl_usd: float
    safety_score: int
    opportunity_score: int
    confidence_score: int
    risk_level: str
    incident_count: int
    audit_count: int
    deployment_count: int


class DefiRateComparisonResponse(BaseModel):
    asset: str
    markets_found: int
    best_supply: List[LendingMarketResponse] = []
    lowest_borrow: List[LendingMarketResponse] = []
    all_markets: List[LendingMarketResponse] = []


class DefiDeploymentResponse(BaseModel):
    chain: str
    display_name: str
    tvl_usd: Optional[float] = None
    share_pct: Optional[float] = None
    deployment_key: str


class DefiOpportunityResponse(BaseModel):
    id: str
    kind: str
    product_type: Optional[str] = None
    score_family: Optional[str] = None
    title: str
    subtitle: str
    protocol: str
    protocol_name: str
    protocol_slug: str
    project: str
    symbol: str
    chain: str
    apy: float
    tvl_usd: float
    tags: List[str] = []
    summary: DefiOpportunitySummaryResponse
    dimensions: List[OpportunityDimensionResponse] = []
    confidence: Optional[DefiConfidenceResponse] = None
    score_caps: List[DefiScoreCapResponse] = []
    evidence: List[DefiEvidenceItemResponse] = []
    scenarios: List[DefiScenarioItemResponse] = []
    dependencies: List[DefiDependencyResponse] = []
    assets: List[DefiAssetProfileResponse] = []
    deployment: Dict[str, Any] = {}
    ranking_profile: Optional[str] = None
    raw: Dict[str, Any] = {}
    history: Optional[DefiOpportunityHistoryResponse] = None
    protocol_profile: Optional[Dict[str, Any]] = None
    related_opportunities: List[Dict[str, Any]] = []
    rate_comparison: Optional[DefiRateComparisonResponse] = None
    safer_alternative: Optional[Dict[str, Any]] = None
    ai_analysis: Optional[DefiOpportunityAIAnalysisResponse] = None


class DefiProtocolProfileResponse(BaseModel):
    protocol: str
    display_name: str
    slug: str
    category: Optional[str] = None
    url: Optional[str] = None
    logo: Optional[str] = None
    chains: List[str] = []
    ranking_profile: Optional[str] = None
    summary: DefiProtocolSummaryResponse
    dimensions: List[OpportunityDimensionResponse] = []
    confidence: Optional[DefiConfidenceResponse] = None
    chain_breakdown: List[Dict[str, Any]] = []
    deployments: List[DefiDeploymentResponse] = []
    top_markets: List[LendingMarketResponse] = []
    top_pools: List[PoolResponse] = []
    top_opportunities: List[DefiOpportunityResponse] = []
    audits: List[Dict[str, Any]] = []
    incidents: List[Dict[str, Any]] = []
    evidence: List[DefiEvidenceItemResponse] = []
    scenarios: List[DefiScenarioItemResponse] = []
    dependencies: List[DefiDependencyResponse] = []
    assets: List[DefiAssetProfileResponse] = []
    docs_profile: Dict[str, Any] = {}
    governance: Dict[str, Any] = {}
    methodology: Dict[str, str] = {}
    ai_analysis: Optional[DefiProtocolAIAnalysisResponse] = None


class DefiAnalyzerResponse(BaseModel):
    query: Optional[str] = None
    chain: Optional[str] = None
    ranking_profile: Optional[str] = None
    public_ranking_default: str = "balanced"
    count: Dict[str, int] = {}
    summary: Dict[str, Any] = {}
    highlights: Dict[str, Any] = {}
    top_pools: List[PoolResponse] = []
    top_yields: List[YieldOpportunityResponse] = []
    top_lending_markets: List[LendingMarketResponse] = []
    top_opportunities: List[DefiOpportunityResponse] = []
    protocol_spotlights: List[DefiProtocolMatchResponse] = []
    matching_protocols: List[DefiProtocolMatchResponse] = []
    methodology: Dict[str, str] = {}
    ai_market_brief: Optional[DefiMarketBriefResponse] = None
    data_source: str = "DefiLlama"


class DefiOpportunitiesListResponse(BaseModel):
    opportunities: List[DefiOpportunityResponse] = []
    count: int
    summary: Dict[str, Any] = {}
    highlights: Dict[str, Any] = {}
    methodology: Dict[str, str] = {}
    filters: Dict[str, Any] = {}
    ai_market_brief: Optional[DefiMarketBriefResponse] = None
    data_source: str = "DefiLlama"


class DefiCompareRowResponse(BaseModel):
    opportunity_id: str
    protocol: str
    chain: str
    asset: str
    apy: float
    opportunity_score: int
    safety_score: int
    yield_quality_score: int
    exit_quality_score: int
    confidence_score: int
    headline: str


class DefiCompareResponse(BaseModel):
    asset: str
    chain: Optional[str] = None
    mode: str = "supply"
    ranking_profile: str = "balanced"
    summary: Dict[str, Any] = {}
    matrix: List[DefiCompareRowResponse] = []
    opportunities: List[DefiOpportunityResponse] = []
    methodology: Dict[str, str] = {}
    ai_market_brief: Optional[DefiMarketBriefResponse] = None


class DefiSimulationScenarioResponse(BaseModel):
    name: str
    summary: str
    metric: str
    value: float
    unit: str
    severity: str


class DefiSimulationResponse(BaseModel):
    kind: str
    summary: str
    base_case: Dict[str, Any] = {}
    scenarios: List[DefiSimulationScenarioResponse] = []
    recommendations: List[str] = []


class DefiPositionAnalysisResponse(DefiSimulationResponse):
    position_size_usd: float = 0.0
    monitor_triggers: List[str] = []


# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENCE PLATFORM RESPONSE (REKT / AUDITS)
# ═══════════════════════════════════════════════════════════════════════════

class RektIncidentResponse(BaseModel):
    """Single exploit or hack incident."""
    id: str
    name: str
    date: str
    protocol: str
    chains: List[str] = []
    attack_type: str
    amount_usd: float
    description: str
    post_mortem_url: str = ""
    funds_recovered: bool = False
    severity: str = "MEDIUM"


class RektListResponse(BaseModel):
    """List of incidents."""
    incidents: List[RektIncidentResponse]
    count: int
    total_stolen_usd: float
    filters: Dict[str, Any] = {}


class AuditResponse(BaseModel):
    """Protocol audit record."""
    id: str
    protocol: str
    auditor: str
    date: str
    report_url: str = ""
    severity_findings: Dict[str, int] = {}
    verdict: str = "PASS"
    chains: List[str] = []


class AuditsListResponse(BaseModel):
    """List of audits."""
    audits: List[AuditResponse]
    count: int
    filters: Dict[str, Any] = {}


# ═══════════════════════════════════════════════════════════════════════════
# UNIVERSAL SEARCH RESPONSE
# ═══════════════════════════════════════════════════════════════════════════

class SearchResultItem(BaseModel):
    """Single universal search result"""
    type: str  # token / protocol / wallet / pool / audit / rekt
    product_type: Optional[str] = None
    title: str
    subtitle: str
    address: Optional[str] = None
    chain: Optional[str] = None
    score: Optional[float] = None  # Relevance or safety score
    url: Optional[str] = None     # Internal navigation URL
    logo: Optional[str] = None


class UniversalSearchResponse(BaseModel):
    """Universal search results"""
    query: str
    results: List[SearchResultItem]
    total: int
    input_type: str = "search_query"  # evm_address / solana_address / search_query / ens_domain
