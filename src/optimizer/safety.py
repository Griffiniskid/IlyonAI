from __future__ import annotations

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
