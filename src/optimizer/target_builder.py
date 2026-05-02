from __future__ import annotations

from src.optimizer.snapshot import PortfolioPosition, PortfolioSnapshot


def build_target_positions(snapshot: PortfolioSnapshot, *, protocol: str = "aave-v3") -> list[PortfolioPosition]:
    return [
        position.model_copy(update={"protocol": protocol, "apy": max(position.apy, 4.8), "sentinel": max(position.sentinel, 82)})
        for position in snapshot.positions
    ]


def build_target(holdings: list[dict], *, risk_budget: str = "balanced", total_usd: float | None = None) -> list[dict]:
    """Placeholder — Task 3.2 replaces with real target-building logic."""
    raise NotImplementedError("build_target not yet implemented")
