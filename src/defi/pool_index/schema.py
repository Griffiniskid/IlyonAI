"""Pool Index record schema (matches alembic agent_005 pool_index table)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class PoolRecord:
    """Single row in the pool_index table.

    `pool_id` is the canonical identifier — for EVM V3-class pools it's
    typically the pool contract address; for V4 it's the keccak hash of
    the PoolKey; for Solana it's the pool's account pubkey.
    """

    pool_id: str
    chain_id: int
    protocol: str
    protocol_version: str | None
    pool_address: str | None
    pool_key_hash: str | None
    pool_pubkey: str | None
    token0_address: str
    token1_address: str | None
    token2_address: str | None
    fee_bps: int | None
    tick_spacing: int | None
    bin_step_bps: int | None
    hooks_address: str | None
    tvl_usd: Decimal | None
    volume_7d_usd: Decimal | None
    fee_apr_30d: float | None
    reward_apr_30d: float | None
    pool_age_days: int | None
    audit_status: str | None
    shield_status: str | None
    last_refreshed: datetime

    @property
    def total_apr(self) -> float:
        return float(self.fee_apr_30d or 0.0) + float(self.reward_apr_30d or 0.0)

    @property
    def is_clmm(self) -> bool:
        return self.protocol_version in {"v3", "v4", "clmm"} or bool(self.tick_spacing)

    @property
    def is_dlmm(self) -> bool:
        return self.protocol_version == "dlmm" or bool(self.bin_step_bps)
