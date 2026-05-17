"""Spec §5e — Per-execution dust tracker.

Multi-leg signable executions (e.g., swap → swap → LP-add) leave small
residual balances of intermediate tokens at every hop. Each individual
leftover may be sub-cent, but the cumulative dust across a 3-5 leg plan
routinely exceeds $1 — high enough to be worth resolving with a final
"sweep to USDC", "leave as-is", or "increase position" prompt.

This module ships the pure accumulator. The runtime / execution
post-step hook records `(step_id, token, amount_token, amount_usd)`
after each leg settles; once `cumulative_usd() >= threshold_usd` the
caller surfaces `to_resolve_card()` to the frontend as a DustResolve
card. Spec §5e — per-leg dust + cumulative > $1 prompts sweep/leave/
increase.

The tracker is intentionally execution-local (one instance per plan
execution). It does NOT persist across plans and does NOT decide which
action to take — that's the user's choice via the card actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class DustDelta:
    step_id: str
    token: str
    amount_token: float
    amount_usd: float


@dataclass
class DustTracker:
    threshold_usd: float = 1.00
    _deltas: list[DustDelta] = field(default_factory=list)

    def record(
        self,
        step_id: str,
        token: str,
        amount_token: float,
        amount_usd: float,
    ) -> None:
        """Append a per-leg dust delta. Called from the execution
        post-step hook after each leg settles on-chain.
        """
        self._deltas.append(
            DustDelta(
                step_id=step_id,
                token=token,
                amount_token=amount_token,
                amount_usd=amount_usd,
            )
        )

    def cumulative_usd(self) -> float:
        """Sum of all recorded dust deltas in USD."""
        return sum(d.amount_usd for d in self._deltas)

    def should_resolve(self) -> bool:
        """True once cumulative dust crosses `threshold_usd` ($1 default)."""
        return self.cumulative_usd() >= self.threshold_usd

    def to_resolve_card(self) -> dict:
        """Frontend card payload — kind `dust_resolve`, surfaces total
        USD, per-leg breakdown, and the three user actions per §5e.
        """
        return {
            "kind": "dust_resolve",
            "total_usd": round(self.cumulative_usd(), 4),
            "deltas": [asdict(d) for d in self._deltas],
            "actions": ["sweep_to_usdc", "leave", "increase_position"],
        }
