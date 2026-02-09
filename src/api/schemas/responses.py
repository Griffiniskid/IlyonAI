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
    liquidity_locked: bool
    lp_lock_percent: float
    honeypot_status: str
    honeypot_is_honeypot: bool
    honeypot_sell_tax_percent: Optional[float] = None
    honeypot_explanation: str
    honeypot_warnings: List[str] = []


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
    quick_score: Optional[int] = None  # Quick analysis score if available


class TrendingResponse(BaseModel):
    """Trending tokens list response"""
    tokens: List[TrendingTokenResponse]
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    category: str = "trending"  # trending, gainers, losers, new

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
    value: int
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
    active_tokens: int  # Number of tokens being tracked
    active_tokens_change: int
    safe_tokens_percent: float  # % of tracked tokens classified as safe
    safe_tokens_change: float
    scams_detected: int  # Risky + Scam tokens count
    scams_change: int

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
