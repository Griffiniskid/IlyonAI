"""Session-key policy model — §11 D.5/D.6 off-chain enforcement.

Mirrors the agent_007 session_key_policies schema. Used by autonomous
flows to check whether the in-flight action falls inside the active
policy envelope (spend caps, allowed protocols, expiry, revocation).

On-chain enforcement (Biconomy Nexus / ZeroDev policy framework) is the
Phase 7 follow-up; this off-chain index is the source of truth for the
runtime's autonomous-action gate.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable


@dataclass
class SessionKeyPolicy:
    policy_id: str
    user_wallet: str
    chain_id: int
    scope: str                              # human-readable scope, e.g. "aave-v3 supply USDC"
    allowed_protocols: tuple[str, ...] = ()  # ("aave-v3", "compound-v3")
    allowed_actions: tuple[str, ...] = ()   # ("supply", "withdraw", "claim")
    allowed_assets: tuple[str, ...] = ()    # ("USDC", "USDT")
    spend_cap_24h_usd: Decimal | None = None
    spend_cap_total_usd: Decimal | None = None
    spent_24h_usd: Decimal = Decimal("0")
    spent_total_usd: Decimal = Decimal("0")
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime | None = None

    @classmethod
    def new(
        cls, *,
        user_wallet: str,
        chain_id: int,
        scope: str,
        allowed_protocols: Iterable[str] = (),
        allowed_actions: Iterable[str] = (),
        allowed_assets: Iterable[str] = (),
        spend_cap_24h_usd: Decimal | float | None = None,
        spend_cap_total_usd: Decimal | float | None = None,
        expires_at: datetime | None = None,
    ) -> "SessionKeyPolicy":
        return cls(
            policy_id=str(uuid.uuid4()),
            user_wallet=user_wallet.lower(),
            chain_id=int(chain_id),
            scope=scope,
            allowed_protocols=tuple(p.lower() for p in allowed_protocols),
            allowed_actions=tuple(a.lower() for a in allowed_actions),
            allowed_assets=tuple(a.upper() for a in allowed_assets),
            spend_cap_24h_usd=Decimal(str(spend_cap_24h_usd)) if spend_cap_24h_usd is not None else None,
            spend_cap_total_usd=Decimal(str(spend_cap_total_usd)) if spend_cap_total_usd is not None else None,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )

    def is_active(self, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.revoked_at is not None and self.revoked_at <= now:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True

    def can_authorise(
        self, *,
        protocol: str,
        action: str,
        asset: str,
        amount_usd: Decimal | float,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        """Return (allowed, reason). reason is empty on True; explanation on False."""
        if not self.is_active(now=now):
            return False, "policy is revoked or expired"
        if self.allowed_protocols and protocol.lower() not in self.allowed_protocols:
            return False, f"protocol {protocol!r} not in {list(self.allowed_protocols)}"
        if self.allowed_actions and action.lower() not in self.allowed_actions:
            return False, f"action {action!r} not in {list(self.allowed_actions)}"
        if self.allowed_assets and asset.upper() not in self.allowed_assets:
            return False, f"asset {asset!r} not in {list(self.allowed_assets)}"
        amt = Decimal(str(amount_usd))
        if amt <= 0:
            return False, "amount_usd must be positive"
        if self.spend_cap_24h_usd is not None and self.spent_24h_usd + amt > self.spend_cap_24h_usd:
            return False, (
                f"24h spend cap exceeded: spent={self.spent_24h_usd} + "
                f"{amt} > cap={self.spend_cap_24h_usd}"
            )
        if self.spend_cap_total_usd is not None and self.spent_total_usd + amt > self.spend_cap_total_usd:
            return False, (
                f"total spend cap exceeded: spent={self.spent_total_usd} + "
                f"{amt} > cap={self.spend_cap_total_usd}"
            )
        return True, ""

    def record_spend(self, amount_usd: Decimal | float) -> None:
        amt = Decimal(str(amount_usd))
        if amt <= 0:
            return
        self.spent_24h_usd += amt
        self.spent_total_usd += amt

    def to_row(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "user_wallet": self.user_wallet,
            "chain_id": self.chain_id,
            "scope": self.scope,
            "allowed_protocols_json": json.dumps(list(self.allowed_protocols)),
            "allowed_actions_json": json.dumps(list(self.allowed_actions)),
            "allowed_assets_json": json.dumps(list(self.allowed_assets)),
            "spend_cap_24h_usd": str(self.spend_cap_24h_usd) if self.spend_cap_24h_usd is not None else None,
            "spend_cap_total_usd": str(self.spend_cap_total_usd) if self.spend_cap_total_usd is not None else None,
            "spent_24h_usd": str(self.spent_24h_usd),
            "spent_total_usd": str(self.spent_total_usd),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def revoke_policy(policy: SessionKeyPolicy, *, at: datetime | None = None) -> SessionKeyPolicy:
    policy.revoked_at = at or datetime.now(timezone.utc)
    return policy
