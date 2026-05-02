from __future__ import annotations

from pydantic import BaseModel, Field


class PortfolioPosition(BaseModel):
    protocol: str
    token: str
    chain: str
    usd_value: float
    apy: float
    sentinel: int


class PortfolioSnapshot(BaseModel):
    user_id: int
    positions: list[PortfolioPosition] = Field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return sum(position.usd_value for position in self.positions)

    @property
    def blended_sentinel(self) -> int | None:
        total = self.total_usd
        if total <= 0:
            return None
        return round(sum(position.sentinel * position.usd_value for position in self.positions) / total)


async def snapshot_from_user(wallet: str) -> list[dict]:
    """Placeholder — Task 3.2 replaces with real RPC-backed snapshot."""
    raise NotImplementedError("snapshot_from_user not yet implemented")
