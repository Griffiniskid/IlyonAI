"""
API Request schemas for the Ilyon AI Web API.

Pydantic models that define the structure of all API requests.
"""

from pydantic import BaseModel, Field, model_validator, validator
from typing import Optional, List
from enum import Enum
import re


class AnalysisModeType(str, Enum):
    """Analysis mode options"""
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


# ═══════════════════════════════════════════════════════════════════════════
# ANALYSIS REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class AnalyzeTokenRequest(BaseModel):
    """Request to analyze a token — supports all chains"""
    address: str = Field(..., min_length=32, max_length=66)
    mode: AnalysisModeType = AnalysisModeType.STANDARD
    chain: Optional[str] = None  # Auto-detected if omitted

    @validator('address')
    def validate_address(cls, v):
        """Accept Solana base58 OR EVM 0x hex addresses"""
        v = v.strip()
        # EVM address: 0x + 40 hex chars
        evm_pattern = re.compile(r'^0x[0-9a-fA-F]{40}$')
        # Solana address: base58, 32-44 chars
        solana_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if evm_pattern.match(v) or solana_pattern.match(v):
            return v
        raise ValueError('Invalid token address format — must be a Solana base58 or EVM 0x address')


class RefreshAnalysisRequest(BaseModel):
    """Request to refresh/re-analyze a token"""
    address: str = Field(..., min_length=32, max_length=66)
    force: bool = False  # Force refresh even if cached
    chain: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# CONTRACT SCANNER REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class ContractScanRequest(BaseModel):
    """Request to scan a smart contract"""
    address: str = Field(..., min_length=32, max_length=66)
    chain: str = "ethereum"

    @validator('address')
    def validate_address(cls, v):
        v = v.strip()
        evm_pattern = re.compile(r'^0x[0-9a-fA-F]{40}$')
        solana_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if evm_pattern.match(v) or solana_pattern.match(v):
            return v
        raise ValueError('Invalid contract address format')


# ═══════════════════════════════════════════════════════════════════════════
# SHIELD / APPROVAL REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class ShieldScanRequest(BaseModel):
    """Request to scan wallet approvals"""
    wallet: str = Field(..., min_length=32, max_length=66)
    chains: Optional[List[str]] = None  # None = all chains

    @validator('wallet')
    def validate_wallet(cls, v):
        v = v.strip()
        evm_pattern = re.compile(r'^0x[0-9a-fA-F]{40}$')
        solana_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if evm_pattern.match(v) or solana_pattern.match(v):
            return v
        raise ValueError('Invalid wallet address format')


class RevokePreparationRequest(BaseModel):
    """Request to prepare a revoke transaction"""
    token_address: str
    spender_address: str
    chain: str


# ═══════════════════════════════════════════════════════════════════════════
# DEFI REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class PoolsFilterRequest(BaseModel):
    """Filter for pool explorer"""
    chain: Optional[str] = None
    dex: Optional[str] = None
    min_tvl: float = Field(default=10000, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class YieldsFilterRequest(BaseModel):
    """Filter for yield opportunities"""
    chain: Optional[str] = None
    min_tvl: float = Field(default=50000, ge=0)
    min_apy: float = Field(default=0, ge=0)
    max_apy: float = Field(default=10000, ge=0)
    stable_only: bool = False
    audited_only: bool = False
    limit: int = Field(default=50, ge=1, le=200)


class DefiCompareRequest(BaseModel):
    """Entity-first compare request for DeFi opportunities."""
    asset: str = Field(..., min_length=1, max_length=20)
    chain: Optional[str] = None
    protocols: List[str] = []
    mode: str = "supply"
    ranking_profile: str = "balanced"


class AnalyzePoolRequest(BaseModel):
    """Request to analyze a single DeFi pool."""
    pool_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    pair_address: Optional[str] = Field(default=None, min_length=1, max_length=200)
    chain: Optional[str] = None
    source: Optional[str] = Field(default=None, pattern="^(defillama|dexpair)$")
    include_ai: bool = True
    ranking_profile: str = "balanced"
    kind: Optional[str] = Field(default=None, pattern="^(pool|yield)$")

    @model_validator(mode="after")
    def validate_identifier(self):
        if not self.pool_id and not self.pair_address:
            raise ValueError("Either pool_id or pair_address is required")
        return self


class DefiLPSimulationRequest(BaseModel):
    """Request to simulate LP or farm stress."""
    deposit_usd: float = Field(..., gt=0)
    apy: float = Field(..., ge=0)
    tvl_usd: float = Field(..., gt=0)
    price_move_pct: float = 0
    emissions_decay_pct: float = 0
    stable_depeg_pct: float = 0


class DefiLendingSimulationRequest(BaseModel):
    """Request to simulate lending stress."""
    collateral_usd: float = Field(..., ge=0)
    debt_usd: float = Field(..., ge=0)
    liquidation_threshold: float = Field(default=0.8, ge=0, le=1)
    collateral_drop_pct: float = 0
    stable_depeg_pct: float = 0
    borrow_rate_spike_pct: float = 0
    utilization_pct: float = Field(default=0, ge=0, le=100)
    utilization_shock_pct: float = Field(default=0, ge=0, le=100)


class DefiPositionAnalysisRequest(BaseModel):
    """Request to analyze a DeFi position or hypothetical setup."""
    kind: str = Field(..., pattern="^(lp|lending)$")
    deposit_usd: Optional[float] = Field(default=None, ge=0)
    apy: Optional[float] = Field(default=None, ge=0)
    tvl_usd: Optional[float] = Field(default=None, ge=0)
    collateral_usd: Optional[float] = Field(default=None, ge=0)
    debt_usd: Optional[float] = Field(default=None, ge=0)
    liquidation_threshold: Optional[float] = Field(default=0.8, ge=0, le=1)
    price_move_pct: Optional[float] = 0
    emissions_decay_pct: Optional[float] = 0
    stable_depeg_pct: Optional[float] = 0
    borrow_rate_spike_pct: Optional[float] = 0
    utilization_pct: Optional[float] = Field(default=0, ge=0, le=100)
    utilization_shock_pct: Optional[float] = Field(default=0, ge=0, le=100)


# ═══════════════════════════════════════════════════════════════════════════
# PORTFOLIO REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class TrackWalletRequest(BaseModel):
    """Request to track a wallet — multi-chain"""
    address: str = Field(..., min_length=32, max_length=66)
    label: Optional[str] = Field(None, max_length=50)
    chain: Optional[str] = None  # Auto-detected if omitted

    @validator('address')
    def validate_address(cls, v):
        v = v.strip()
        evm_pattern = re.compile(r'^0x[0-9a-fA-F]{40}$')
        solana_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if evm_pattern.match(v) or solana_pattern.match(v):
            return v
        raise ValueError('Invalid wallet address format')


class UpdateWalletLabelRequest(BaseModel):
    """Request to update wallet label"""
    label: str = Field(..., max_length=50)


# ═══════════════════════════════════════════════════════════════════════════
# WHALE TRACKER REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class WhaleFilterRequest(BaseModel):
    """Request to filter whale transactions"""
    token_address: Optional[str] = None
    wallet_address: Optional[str] = None
    min_amount_usd: float = Field(default=10000, ge=1000)
    type: Optional[str] = None  # "buy" or "sell"
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# ═══════════════════════════════════════════════════════════════════════════
# ALERTS REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class AlertTypeEnum(str, Enum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    SCORE_BELOW = "score_below"
    WHALE_ACTIVITY = "whale_activity"
    CONTRACT_RISK = "contract_risk"       # Approval you granted becomes risky
    PORTFOLIO_SCORE = "portfolio_score"   # Token drops below safety threshold
    EXPLOIT_ALERT = "exploit_alert"       # Protocol you use gets hacked


class CreateAlertRequest(BaseModel):
    """Request to create an alert"""
    token_address: str = Field(..., min_length=32, max_length=66)
    alert_type: AlertTypeEnum
    threshold: float = Field(..., gt=0)
    chain: Optional[str] = None


class UpdateAlertRequest(BaseModel):
    """Request to update an alert"""
    enabled: Optional[bool] = None
    threshold: Optional[float] = Field(None, gt=0)


# ═══════════════════════════════════════════════════════════════════════════
# AUTH REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class AuthChallengeRequest(BaseModel):
    """Request for authentication challenge"""
    wallet_address: str = Field(..., min_length=32, max_length=66)

    @validator('wallet_address')
    def validate_wallet(cls, v):
        v = v.strip()
        evm_pattern = re.compile(r'^0x[0-9a-fA-F]{40}$')
        solana_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if evm_pattern.match(v) or solana_pattern.match(v):
            return v
        raise ValueError('Invalid wallet address format')


class AuthVerifyRequest(BaseModel):
    """Request to verify signed challenge"""
    wallet_address: str = Field(..., min_length=32, max_length=66)
    signature: str = Field(..., min_length=64)
    challenge: str = Field(..., min_length=10)


# ═══════════════════════════════════════════════════════════════════════════
# SEARCH REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class SearchTokensRequest(BaseModel):
    """Request to search tokens"""
    query: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=50)
    chain: Optional[str] = None  # Filter by chain


# ═══════════════════════════════════════════════════════════════════════════
# DEVELOPER API REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class CreateAPIKeyRequest(BaseModel):
    """Request to create a developer API key"""
    label: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class WebhookSubscriptionRequest(BaseModel):
    """Request to subscribe to webhook events"""
    url: str = Field(..., min_length=10, max_length=500)
    events: List[str]  # e.g. ["token_risk_change", "exploit_detected"]
    token_addresses: Optional[List[str]] = None  # Filter by specific tokens
    chains: Optional[List[str]] = None           # Filter by chains
