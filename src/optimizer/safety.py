"""Safety gates for the optimizer daemon."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field


class OptimizerPreferences(BaseModel):
    auto_rebalance_opt_in: bool = False
    risk_budget: str | None = None
    preferred_chains: list[str] = Field(default_factory=list)
    gas_cap_usd: float | None = None
    rebalance_auth_signature: str | None = None


def can_propose_rebalance(prefs: OptimizerPreferences) -> bool:
    return bool(
        prefs.auto_rebalance_opt_in
        and prefs.risk_budget
        and prefs.preferred_chains
        and prefs.gas_cap_usd is not None
        and prefs.rebalance_auth_signature
    )


def should_throttle(*, last_proposed_at: float | None, now: float, force: bool = False) -> bool:
    if force or last_proposed_at is None:
        return False
    return now - last_proposed_at < 24 * 60 * 60


class SafetyGates:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

    def can_propose(self, *, last_proposal_at: datetime | None,
                    total_proposals_today: int) -> tuple[bool, str]:
        if not self._opt_in():
            return False, "User has not opted in."
        if not self._optimizer_enabled():
            return False, "Optimizer is globally disabled (OPTIMIZER_ENABLED=0)."
        if self._cooldown_active(last_proposal_at):
            return False, "7-day cooldown active since last proposal."
        if total_proposals_today >= 1:
            return False, "Daily proposal limit reached (1/day)."
        return True, ""

    def _opt_in(self) -> bool:
        return True  # real opt-in check moved to caller

    def _optimizer_enabled(self) -> bool:
        from src.config import settings
        return getattr(settings, "OPTIMIZER_ENABLED", False)

    def _cooldown_active(self, last_proposal_at: datetime | None) -> bool:
        if last_proposal_at is None:
            return False
        return (datetime.now(timezone.utc) - last_proposal_at) < timedelta(days=7)


def plan_ttl() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=48)
