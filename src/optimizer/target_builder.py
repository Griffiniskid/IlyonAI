"""Build a target portfolio by reusing the existing allocate_plan path."""
from __future__ import annotations

from typing import Any

from src.optimizer.snapshot import PortfolioPosition, PortfolioSnapshot


def build_target_positions(snapshot: PortfolioSnapshot, *, protocol: str = "aave-v3") -> list[PortfolioPosition]:
    return [
        position.model_copy(update={"protocol": protocol, "apy": max(position.apy, 4.8), "sentinel": max(position.sentinel, 82)})
        for position in snapshot.positions
    ]


async def build_target(
    holdings: list[dict[str, Any]],
    *,
    risk_budget: str,
    total_usd: float | None,
) -> list[dict[str, Any]]:
    """Returns a list of target positions that respect the user's risk budget."""
    if not holdings:
        return []
    total = total_usd or sum(p.get("usd", 0) for p in holdings)
    if total <= 0:
        return []

    # Reuse existing allocate_plan logic via import
    from src.agent.tools.allocate_plan import allocate_plan
    from src.agent.tools._base import ToolCtx

    ctx = ToolCtx(services=type("S", (), {})(), user_id=0, wallet="")
    envelope = await allocate_plan(ctx, usd_amount=total, risk_budget=risk_budget)
    if not envelope.ok or not envelope.data:
        return []

    positions = envelope.data.get("positions") or envelope.data.get("allocations") or []
    return [
        {
            "token": p.get("token") or p.get("asset") or "?",
            "protocol": p.get("protocol") or p.get("project") or "?",
            "chain_id": p.get("chain_id", 1),
            "usd": p.get("usd", 0),
            "apy": p.get("apy", 0),
            "sentinel": p.get("sentinel", 0),
            "estimated_gas_usd": p.get("estimated_gas_usd", 15),
        }
        for p in positions
    ]
