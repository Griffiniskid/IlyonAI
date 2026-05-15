"""Background refresher for the pool_index table (dev-plan §1.2).

Pulls DefiLlama Yields snapshot every N minutes (default 30) and writes
into pool_index via upsert_pools. Runs as an aiohttp on_startup task
under app['_pool_index_refresher_task'].

Per-protocol subgraph + Merkl APR enrichment are stub points that can
be wired later without touching the rest of the runtime.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from aiohttp import web

from src.defi.pool_index.store import upsert_pools

logger = logging.getLogger(__name__)

_LLAMA_POOLS = "https://yields.llama.fi/pools"
_LLAMA_PROJECT_TO_PROTOCOL: dict[str, str] = {
    "aave-v3": "aave-v3",
    "compound-v3": "compound-v3",
    "uniswap-v3": "uniswap-v3",
    "uniswap-v4": "uniswap-v4",
    "pancakeswap-amm-v3": "pancakeswap-v3",
    "aerodrome-v1": "aerodrome",
    "aerodrome-slipstream": "aerodrome-slipstream",
    "velodrome-v2": "velodrome-v2",
    "velodrome-v3": "velodrome-cl",
    "curve-dex": "curve",
    "balancer-v2": "balancer-v2",
    "balancer-v3": "balancer-v3",
    "morpho-blue": "morpho-blue",
    "spark": "spark",
    "lido": "lido",
    "rocket-pool": "rocket-pool",
    "ether.fi-stake": "ether.fi",
    "raydium-amm": "raydium-amm",
    "raydium-clmm": "raydium-clmm",
    "orca-whirlpool": "orca-whirlpools",
    "meteora-dlmm": "meteora-dlmm",
    "kamino-vaults": "kamino",
    "marinade-finance": "marinade",
    "jito-staking": "jito",
}
_CHAIN_NAME_TO_ID: dict[str, int] = {
    "Ethereum": 1, "Polygon": 137, "Arbitrum": 42161, "Optimism": 10,
    "Base": 8453, "BSC": 56, "Avalanche": 43114, "Solana": 0,
    "Unichain": 130, "Linea": 59144, "Scroll": 534352, "Mantle": 5000,
    "Blast": 81457, "zkSync Era": 324, "Gnosis": 100, "Celo": 42220,
    "Sonic": 146, "Berachain": 80094,
}


async def _fetch_llama_pools(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    r = await client.get(_LLAMA_POOLS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("data", []) if isinstance(data, dict) else data


def _llama_pool_to_record(pool: dict[str, Any]) -> dict[str, Any] | None:
    project_raw = (pool.get("project") or "").lower()
    protocol = _LLAMA_PROJECT_TO_PROTOCOL.get(project_raw)
    if not protocol:
        return None
    chain_name = pool.get("chain") or ""
    chain_id = _CHAIN_NAME_TO_ID.get(chain_name)
    if chain_id is None:
        return None
    pool_id = str(pool.get("pool") or "")
    if not pool_id:
        return None
    underlying = pool.get("underlyingTokens") or []
    token0 = (underlying[0] if len(underlying) >= 1 else "0x0").lower()
    token1 = (underlying[1].lower() if len(underlying) >= 2 else None)
    token2 = (underlying[2].lower() if len(underlying) >= 3 else None)
    tvl = pool.get("tvlUsd")
    volume_7d = (pool.get("volumeUsd7d") or pool.get("volumeUsd1d"))
    apy_base = pool.get("apyBase") or 0.0
    apy_reward = pool.get("apyReward") or 0.0
    return {
        "pool_id": pool_id,
        "chain_id": chain_id,
        "protocol": protocol,
        "protocol_version": pool.get("poolMeta") or "",
        "pool_address": pool_id if chain_name != "Solana" else None,
        "pool_pubkey": pool_id if chain_name == "Solana" else None,
        "pool_key_hash": None,
        "token0_address": token0,
        "token1_address": token1,
        "token2_address": token2,
        "fee_bps": None,
        "tick_spacing": None,
        "bin_step_bps": None,
        "hooks_address": None,
        "tvl_usd": Decimal(str(tvl)) if tvl is not None else None,
        "volume_7d_usd": Decimal(str(volume_7d)) if volume_7d is not None else None,
        "fee_apr_30d": float(apy_base) if apy_base else 0.0,
        "reward_apr_30d": float(apy_reward) if apy_reward else 0.0,
        "pool_age_days": None,
        "audit_status": None,
        "shield_status": None,
        "last_refreshed": datetime.now(timezone.utc),
        "metadata_json": None,
    }


async def refresh_pool_index(session_factory: Any) -> dict[str, int]:
    """Pull DefiLlama Yields → upsert into pool_index. Returns counts."""
    counters = {"fetched": 0, "indexable": 0, "upserted": 0}
    async with httpx.AsyncClient() as client:
        pools = await _fetch_llama_pools(client)
    counters["fetched"] = len(pools)
    records: list[dict[str, Any]] = []
    for p in pools:
        rec = _llama_pool_to_record(p)
        if rec:
            records.append(rec)
    counters["indexable"] = len(records)
    if not records:
        return counters
    async with session_factory() as session:
        n = await upsert_pools(session, records)
        await session.commit()
        counters["upserted"] = n
    return counters


async def _refresher_loop(app: web.Application, interval_s: int) -> None:
    """Long-running refresher task. Cancelled cleanly on shutdown."""
    session_factory = app.get("_db_session_factory")
    if session_factory is None:
        logger.warning("Pool-index refresher: no _db_session_factory in app; idling.")
        return
    while True:
        try:
            counts = await refresh_pool_index(session_factory)
            logger.info("pool_index refresh: %s", counts)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("pool_index refresh failed: %s", exc, exc_info=True)
        await asyncio.sleep(interval_s)


def start_pool_index_refresher(app: web.Application, *, interval_minutes: int = 30) -> None:
    async def _on_startup(app: web.Application) -> None:
        task = asyncio.create_task(
            _refresher_loop(app, interval_s=interval_minutes * 60),
            name="pool_index_refresher",
        )
        app["_pool_index_refresher_task"] = task

    async def _on_cleanup(app: web.Application) -> None:
        task = app.get("_pool_index_refresher_task")
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
