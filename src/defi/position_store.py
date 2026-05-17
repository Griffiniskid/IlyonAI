"""Read API + insert wrapper for the user_positions table (agent_005).

Phase 4 lifecycle code (decrease / collect / rebalance / withdraw)
reads from this table to find the user's open positions. The receipt
verifier writes a row after `verify()` flips confirmed=True.

Keeps wire-up to actual sqlalchemy session/engine pluggable so callers
can mock the DB for tests.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol


@dataclass
class UserPosition:
    position_id: str
    user_id: int
    wallet_address: str
    chain_id: int
    protocol: str
    pool_id: str
    receipt_kind: str
    receipt_address: str | None = None
    receipt_token_id: str | None = None
    tick_lower: int | None = None
    tick_upper: int | None = None
    bin_lower: int | None = None
    bin_upper: int | None = None
    amount0_deposited: Decimal | None = None
    amount1_deposited: Decimal | None = None
    liquidity: Decimal | None = None
    tx_hash: str = ""
    block_number: int | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    status: str = "open"
    metadata: dict[str, Any] | None = None
    # Solana lifecycle state (V7-004 / agent_010). Stamped onto
    # step.transaction at build time by services/solana-yield-builder
    # adapters; persisted here so close/unstake/withdraw flows can
    # resume after restart without re-deriving from on-chain state.
    redemption_program: str | None = None
    receipt_mint: str | None = None
    lockup_end_ts: int | None = None
    underlying_custody: str | None = None
    position_nft: str | None = None

    @classmethod
    def new(
        cls,
        *,
        user_id: int,
        wallet_address: str,
        chain_id: int,
        protocol: str,
        pool_id: str,
        receipt_kind: str,
        tx_hash: str,
        **extra: Any,
    ) -> "UserPosition":
        return cls(
            position_id=str(uuid.uuid4()),
            user_id=user_id,
            wallet_address=wallet_address.lower(),
            chain_id=chain_id,
            protocol=protocol,
            pool_id=pool_id,
            receipt_kind=receipt_kind,
            tx_hash=tx_hash,
            opened_at=datetime.now(timezone.utc),
            **extra,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "user_id": self.user_id,
            "wallet_address": self.wallet_address,
            "chain_id": self.chain_id,
            "protocol": self.protocol,
            "pool_id": self.pool_id,
            "receipt_kind": self.receipt_kind,
            "receipt_address": self.receipt_address,
            "receipt_token_id": self.receipt_token_id,
            "tick_lower": self.tick_lower,
            "tick_upper": self.tick_upper,
            "bin_lower": self.bin_lower,
            "bin_upper": self.bin_upper,
            "amount0_deposited": str(self.amount0_deposited) if self.amount0_deposited is not None else None,
            "amount1_deposited": str(self.amount1_deposited) if self.amount1_deposited is not None else None,
            "liquidity": str(self.liquidity) if self.liquidity is not None else None,
            "tx_hash": self.tx_hash,
            "block_number": self.block_number,
            "status": self.status,
            "metadata_json": json.dumps(self.metadata) if self.metadata is not None else None,
            "redemption_program": self.redemption_program,
            "receipt_mint": self.receipt_mint,
            "lockup_end_ts": self.lockup_end_ts,
            "underlying_custody": self.underlying_custody,
            "position_nft": self.position_nft,
        }


class _SupportsExecute(Protocol):
    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any: ...


async def insert_position(session: _SupportsExecute, pos: UserPosition) -> None:
    """Insert a single confirmed position into user_positions.

    Caller passes the active sqlalchemy AsyncSession. Use this from the
    receipt-verification path (src/agent/receipt_watcher.py) once
    verify() returns confirmed=True for the broadcast.
    """
    row = pos.to_row()
    columns = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    from sqlalchemy import text
    sql = text(
        f"INSERT INTO user_positions ({columns}) VALUES ({placeholders})"
    )
    await session.execute(sql, row)


async def find_open_positions(
    session: _SupportsExecute,
    *,
    wallet_address: str,
    chain_id: int | None = None,
    protocol: str | None = None,
) -> list[dict[str, Any]]:
    """Return rows for the wallet's open positions, optionally filtered
    by chain or protocol. Phase 4 lifecycle code (rebalance / collect)
    starts here.
    """
    from sqlalchemy import text
    clauses = ["wallet_address = :wallet", "status = 'open'"]
    params: dict[str, Any] = {"wallet": wallet_address.lower()}
    if chain_id is not None:
        clauses.append("chain_id = :chain_id")
        params["chain_id"] = chain_id
    if protocol:
        clauses.append("protocol = :protocol")
        params["protocol"] = protocol
    where = " AND ".join(clauses)
    sql = text(f"SELECT * FROM user_positions WHERE {where} ORDER BY opened_at DESC")
    result = await session.execute(sql, params)
    rows = result.mappings().all() if hasattr(result, "mappings") else list(result)
    return [dict(r) for r in rows]


async def close_position(
    session: _SupportsExecute,
    *,
    position_id: str,
    tx_hash: str,
) -> None:
    """Flip a position to closed after a full decrease+collect+burn flow."""
    from sqlalchemy import text
    sql = text(
        "UPDATE user_positions SET status = 'closed', closed_at = :ts "
        "WHERE position_id = :pid"
    )
    await session.execute(sql, {"pid": position_id, "ts": datetime.now(timezone.utc)})
