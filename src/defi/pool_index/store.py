"""Async read/upsert helpers for the pool_index table (agent_005 schema).

Replaces the 12-row hardcoded catalog at execute_pool_position.py:55-95.
Callers pass an active sqlalchemy AsyncSession.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Protocol


class _SupportsExecute(Protocol):
    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any: ...


_COLUMNS = (
    "pool_id", "chain_id", "protocol", "protocol_version",
    "pool_address", "pool_key_hash", "pool_pubkey",
    "token0_address", "token1_address", "token2_address",
    "fee_bps", "tick_spacing", "bin_step_bps", "hooks_address",
    "tvl_usd", "volume_7d_usd", "fee_apr_30d", "reward_apr_30d",
    "pool_age_days", "audit_status", "shield_status",
    "last_refreshed", "metadata_json",
)


def _normalise_row(record: dict[str, Any]) -> dict[str, Any]:
    out = {k: record.get(k) for k in _COLUMNS}
    if "last_refreshed" not in record:
        out["last_refreshed"] = datetime.now(timezone.utc)
    for d_key in ("tvl_usd", "volume_7d_usd"):
        v = out.get(d_key)
        if v is not None and not isinstance(v, (Decimal, float, int)):
            try:
                out[d_key] = Decimal(str(v))
            except Exception:
                out[d_key] = None
    if "metadata_json" in record and not isinstance(record["metadata_json"], str):
        out["metadata_json"] = json.dumps(record["metadata_json"]) if record["metadata_json"] else None
    return out


async def upsert_pool(session: _SupportsExecute, record: dict[str, Any]) -> None:
    """ON CONFLICT (pool_id) DO UPDATE — postgres-only upsert."""
    from sqlalchemy import text
    row = _normalise_row(record)
    cols = ", ".join(_COLUMNS)
    placeholders = ", ".join(f":{k}" for k in _COLUMNS)
    updates = ", ".join(f"{k}=EXCLUDED.{k}" for k in _COLUMNS if k != "pool_id")
    sql = text(
        f"INSERT INTO pool_index ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT (pool_id) DO UPDATE SET {updates}"
    )
    await session.execute(sql, row)


async def upsert_pools(session: _SupportsExecute, records: Iterable[dict[str, Any]]) -> int:
    """Bulk upsert helper; returns row count emitted."""
    n = 0
    for r in records:
        await upsert_pool(session, r)
        n += 1
    return n


async def find_pool_by_pair(
    session: _SupportsExecute,
    *,
    chain_id: int,
    token0_address: str,
    token1_address: str,
    protocol: str | None = None,
    min_tvl_usd: float | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Symmetric pair lookup — matches both (t0,t1) and (t1,t0) orientations."""
    from sqlalchemy import text
    a = token0_address.lower()
    b = token1_address.lower()
    clauses = [
        "chain_id = :chain_id",
        "((lower(token0_address) = :a AND lower(token1_address) = :b)"
        "  OR (lower(token0_address) = :b AND lower(token1_address) = :a))",
    ]
    params: dict[str, Any] = {"chain_id": chain_id, "a": a, "b": b, "limit": limit}
    if protocol:
        clauses.append("protocol = :protocol")
        params["protocol"] = protocol
    if min_tvl_usd is not None:
        clauses.append("tvl_usd >= :min_tvl")
        params["min_tvl"] = float(min_tvl_usd)
    where = " AND ".join(clauses)
    sql = text(
        f"SELECT * FROM pool_index WHERE {where} "
        f"ORDER BY tvl_usd DESC NULLS LAST LIMIT :limit"
    )
    result = await session.execute(sql, params)
    rows = result.mappings().all() if hasattr(result, "mappings") else list(result)
    return [dict(r) for r in rows]


async def find_pool_by_id(
    session: _SupportsExecute, *, pool_id: str,
) -> dict[str, Any] | None:
    from sqlalchemy import text
    sql = text("SELECT * FROM pool_index WHERE pool_id = :pid LIMIT 1")
    result = await session.execute(sql, {"pid": pool_id})
    rows = result.mappings().all() if hasattr(result, "mappings") else list(result)
    rows = list(rows)
    return dict(rows[0]) if rows else None


async def stale_pool_ids(
    session: _SupportsExecute, *, older_than_minutes: int = 60, limit: int = 500,
) -> list[str]:
    """Identify pool_ids whose last_refreshed is older than the cutoff."""
    from sqlalchemy import text
    sql = text(
        "SELECT pool_id FROM pool_index "
        "WHERE last_refreshed < NOW() - INTERVAL ':n minutes' "
        "ORDER BY last_refreshed ASC LIMIT :limit"
    )
    # SQL INTERVAL doesn't bind cleanly; inject cutoff via Python parametrisation
    sql = text(
        "SELECT pool_id FROM pool_index "
        f"WHERE last_refreshed < NOW() - INTERVAL '{int(older_than_minutes)} minutes' "
        "ORDER BY last_refreshed ASC LIMIT :limit"
    )
    result = await session.execute(sql, {"limit": limit})
    rows = result.mappings().all() if hasattr(result, "mappings") else list(result)
    return [str(r["pool_id"]) for r in rows]
