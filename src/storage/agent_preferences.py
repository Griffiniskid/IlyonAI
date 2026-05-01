"""
Agent preferences storage layer.

Provides CRUD operations for user-specific trading and risk settings.
Uses SQLAlchemy async with SQLite/PostgreSQL compatibility.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.storage.database import Database, AgentPreferencesRow

logger = logging.getLogger(__name__)


@dataclass
class AgentPreferences:
    """User-specific agent preferences for trading and risk management."""
    user_id: int
    risk_budget: str = "balanced"
    preferred_chains: Optional[List[str]] = None
    blocked_protocols: Optional[List[str]] = None
    gas_cap_usd: Optional[float] = None
    slippage_cap_bps: int = 50
    notional_double_confirm_usd: float = 10000.0
    auto_rebalance_opt_in: int = 0
    rebalance_auth_signature: Optional[str] = None
    rebalance_auth_nonce: Optional[int] = None
    updated_at: Optional[datetime] = None

    def as_dict(self) -> Dict[str, Any]:
        """Return preferences as a plain dictionary."""
        return {
            "user_id": self.user_id,
            "risk_budget": self.risk_budget,
            "preferred_chains": self.preferred_chains,
            "blocked_protocols": self.blocked_protocols,
            "gas_cap_usd": self.gas_cap_usd,
            "slippage_cap_bps": self.slippage_cap_bps,
            "notional_double_confirm_usd": self.notional_double_confirm_usd,
            "auto_rebalance_opt_in": self.auto_rebalance_opt_in,
            "rebalance_auth_signature": self.rebalance_auth_signature,
            "rebalance_auth_nonce": self.rebalance_auth_nonce,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def _serialize_json_field(value: Optional[List[str]]) -> Optional[str]:
    """Serialize a list of strings to JSON string for storage."""
    if value is None:
        return None
    return json.dumps(value)


def _deserialize_json_field(value: Any) -> Optional[List[str]]:
    """Deserialize a JSON field back to a list of strings."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return None


async def get_or_default(db: Database, user_id: int) -> AgentPreferences:
    """
    Get agent preferences for a user, or return defaults if none exist.

    Args:
        db: Database instance
        user_id: User identifier

    Returns:
        AgentPreferences instance (stored or default)
    """
    if not db._initialized:
        return AgentPreferences(user_id=user_id)

    async with db.async_session() as session:
        result = await session.execute(
            select(AgentPreferencesRow).where(AgentPreferencesRow.user_id == user_id)
        )
        row = result.scalar_one_or_none()

        if row is None:
            return AgentPreferences(user_id=user_id)

        return AgentPreferences(
            user_id=row.user_id,
            risk_budget=row.risk_budget,
            preferred_chains=_deserialize_json_field(row.preferred_chains),
            blocked_protocols=_deserialize_json_field(row.blocked_protocols),
            gas_cap_usd=row.gas_cap_usd,
            slippage_cap_bps=row.slippage_cap_bps,
            notional_double_confirm_usd=row.notional_double_confirm_usd,
            auto_rebalance_opt_in=row.auto_rebalance_opt_in,
            rebalance_auth_signature=row.rebalance_auth_signature,
            rebalance_auth_nonce=row.rebalance_auth_nonce,
            updated_at=row.updated_at,
        )


async def upsert(db: Database, user_id: int, **kwargs: Any) -> bool:
    """
    Create or update agent preferences for a user.

    Args:
        db: Database instance
        user_id: User identifier
        **kwargs: Fields to update (risk_budget, preferred_chains, etc.)

    Returns:
        True if successful
    """
    if not db._initialized:
        return False

    # Build the values dict
    values: Dict[str, Any] = {"user_id": user_id}
    
    # Handle JSON fields - SQLAlchemy JSON column handles lists natively
    if "preferred_chains" in kwargs:
        values["preferred_chains"] = kwargs.pop("preferred_chains")
    if "blocked_protocols" in kwargs:
        values["blocked_protocols"] = kwargs.pop("blocked_protocols")
    
    # Add remaining fields
    for key, value in kwargs.items():
        values[key] = value
    
    # Always update updated_at
    values["updated_at"] = datetime.utcnow()

    async with db.async_session() as session:
        # Check if row exists
        result = await session.execute(
            select(AgentPreferencesRow).where(AgentPreferencesRow.user_id == user_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing is None:
            # Insert new row
            row = AgentPreferencesRow(**values)
            session.add(row)
        else:
            # Update existing row
            for key, value in values.items():
                if key != "user_id":
                    setattr(existing, key, value)
        
        await session.commit()
        return True
