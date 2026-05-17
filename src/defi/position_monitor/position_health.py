"""PositionHealth snapshot dataclass.

Spec §4: snapshots every 5 min capturing current value, HODL value, fees
collected/uncollected, IL %, in-range bool, time-in-range, realized fee APR.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Optional


@dataclass
class PositionHealth:
    """Health snapshot for a single open DeFi position.

    Fields:
        position_id: stable position identifier (chain + protocol + nft_id / owner+pool).
        chain: chain slug ("ethereum", "arbitrum", "solana", ...).
        protocol: protocol slug ("uniswap_v3", "meteora_dlmm", "aave_v3", ...).
        current_value_usd: USD value of underlying assets + accrued fees right now.
        hodl_value_usd: what the user would hold today if they had NOT entered the LP
            (i.e. the initial token basket valued at current prices).
        fees_collected_usd: lifetime fees the user has already claimed.
        fees_uncollected_usd: fees accrued in-position but not yet claimed.
        il_pct: impermanent loss as a percentage of HODL value. Negative means loss
            (current < hodl), positive means the LP outperformed HODL.
        in_range: True if the position is currently within its active range (V3 / DLMM).
            For V2 / stable-style positions where the concept doesn't apply, callers
            should pass True (always in range) or use a sentinel — None is not supported
            by the bool type but is conceptually "n/a".
        time_in_range_pct: rolling 24h fraction of time spent in-range (0.0 - 100.0).
        realized_fee_apr: fees / value annualized over the rolling measurement window.
        snapshot_at: UTC timestamp the snapshot was captured.
    """

    position_id: str
    chain: str
    protocol: str
    current_value_usd: float
    hodl_value_usd: float
    fees_collected_usd: float
    fees_uncollected_usd: float
    il_pct: float
    in_range: bool
    time_in_range_pct: float
    realized_fee_apr: float
    snapshot_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict (snapshot_at → ISO 8601 string)."""
        return {
            "position_id": self.position_id,
            "chain": self.chain,
            "protocol": self.protocol,
            "current_value_usd": self.current_value_usd,
            "hodl_value_usd": self.hodl_value_usd,
            "fees_collected_usd": self.fees_collected_usd,
            "fees_uncollected_usd": self.fees_uncollected_usd,
            "il_pct": self.il_pct,
            "in_range": self.in_range,
            "time_in_range_pct": self.time_in_range_pct,
            "realized_fee_apr": self.realized_fee_apr,
            "snapshot_at": self.snapshot_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PositionHealth":
        """Reconstruct from a dict produced by `to_dict` (or equivalent)."""
        snapshot_at = d.get("snapshot_at")
        if isinstance(snapshot_at, str):
            snapshot_at = datetime.fromisoformat(snapshot_at)
        elif snapshot_at is None:
            snapshot_at = datetime.utcnow()
        return cls(
            position_id=d["position_id"],
            chain=d["chain"],
            protocol=d["protocol"],
            current_value_usd=float(d["current_value_usd"]),
            hodl_value_usd=float(d["hodl_value_usd"]),
            fees_collected_usd=float(d["fees_collected_usd"]),
            fees_uncollected_usd=float(d["fees_uncollected_usd"]),
            il_pct=float(d["il_pct"]),
            in_range=bool(d["in_range"]),
            time_in_range_pct=float(d["time_in_range_pct"]),
            realized_fee_apr=float(d["realized_fee_apr"]),
            snapshot_at=snapshot_at,
        )


# Sanity check at import time: ensure we still have exactly 12 fields
# (11 health metrics + snapshot_at). If a future edit drops one, callers
# relying on the schema would silently break — fail loud instead.
assert len(fields(PositionHealth)) == 12, (
    "PositionHealth schema changed — update tests + V7-022 snapshot table"
)
