"""
API Request schemas for the AI Sentinel Web API.

Pydantic models that define the structure of all API requests.
"""

from pydantic import BaseModel, Field, validator
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
    """Request to analyze a token"""
    address: str = Field(..., min_length=32, max_length=44)
    mode: AnalysisModeType = AnalysisModeType.STANDARD

    @validator('address')
    def validate_solana_address(cls, v):
        """Validate that address is a valid Solana base58 address"""
        # Basic Solana address validation
        base58_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if not base58_pattern.match(v):
            raise ValueError('Invalid Solana address format')
        return v


class RefreshAnalysisRequest(BaseModel):
    """Request to refresh/re-analyze a token"""
    address: str = Field(..., min_length=32, max_length=44)
    force: bool = False  # Force refresh even if cached


# ═══════════════════════════════════════════════════════════════════════════
# PORTFOLIO REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class TrackWalletRequest(BaseModel):
    """Request to track a wallet"""
    address: str = Field(..., min_length=32, max_length=44)
    label: Optional[str] = Field(None, max_length=50)

    @validator('address')
    def validate_solana_address(cls, v):
        base58_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if not base58_pattern.match(v):
            raise ValueError('Invalid Solana address format')
        return v


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


class CreateAlertRequest(BaseModel):
    """Request to create an alert"""
    token_address: str = Field(..., min_length=32, max_length=44)
    alert_type: AlertTypeEnum
    threshold: float = Field(..., gt=0)

    @validator('address', check_fields=False)
    def validate_solana_address(cls, v):
        base58_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if not base58_pattern.match(v):
            raise ValueError('Invalid Solana address format')
        return v


class UpdateAlertRequest(BaseModel):
    """Request to update an alert"""
    enabled: Optional[bool] = None
    threshold: Optional[float] = Field(None, gt=0)


# ═══════════════════════════════════════════════════════════════════════════
# AUTH REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class AuthChallengeRequest(BaseModel):
    """Request for authentication challenge"""
    wallet_address: str = Field(..., min_length=32, max_length=44)

    @validator('wallet_address')
    def validate_solana_address(cls, v):
        base58_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if not base58_pattern.match(v):
            raise ValueError('Invalid Solana address format')
        return v


class AuthVerifyRequest(BaseModel):
    """Request to verify signed challenge"""
    wallet_address: str = Field(..., min_length=32, max_length=44)
    signature: str = Field(..., min_length=64)
    challenge: str = Field(..., min_length=10)

    @validator('wallet_address')
    def validate_solana_address(cls, v):
        base58_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
        if not base58_pattern.match(v):
            raise ValueError('Invalid Solana address format')
        return v


# ═══════════════════════════════════════════════════════════════════════════
# SEARCH REQUESTS
# ═══════════════════════════════════════════════════════════════════════════

class SearchTokensRequest(BaseModel):
    """Request to search tokens"""
    query: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=50)
