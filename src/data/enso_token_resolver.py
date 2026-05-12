"""Resolve Enso position tokens dynamically via /tokens endpoint.

Maps `(chain_id, protocol_slug, underlying_addr)` → Enso position token
(static atoken / cToken / curve LP / balancer BPT / etc.).

Cached in-process for 24h. Falls back to chain-wide search if exact filter
returns 0 results.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from src.config import settings
from src.routing.enso_client import _pace

_BASE = "https://api.enso.finance/api/v1"
_CACHE_TTL_S = 86400.0


@dataclass(frozen=True)
class EnsoPosition:
    chain_id: int
    protocol_slug: str
    position_address: str
    decimals: int
    underlying_addrs: tuple[str, ...]
    apy: float | None
    apy_base: float | None
    apy_reward: float | None
    tvl: float | None
    primary_address: str
    deposit_type: str  # "SingleToken" | "VariableMultiToken" | "ExactMultiToken"
    redeem_type: str
    raw: dict[str, Any]

    @property
    def is_single_sided(self) -> bool:
        return self.deposit_type == "SingleToken"


_cache: dict[tuple[int, str, str], tuple[float, EnsoPosition | None]] = {}
_cache_lock = asyncio.Lock()

_protocol_alias = {
    "aave-v3": "aave-v3",
    "aave": "aave-v3-prime",
    "aave-v3-prime": "aave-v3-prime",
    "aave-static": "aave-v3-static-atokens",
    "compound-v3": "compound-v3",
    "compound": "compound-v3",
    "curve": "curve-dex",
    "curve-dex": "curve-dex",
    "curve-lending": "curve-lending",
    "balancer": "balancer-v2",
    "balancer-v2": "balancer-v2",
    "balancer-v3": "balancer-v3",
    "yearn-finance": "yearn-v3",
    "yearn": "yearn-v3",
    "yearn-v3": "yearn-v3",
    "morpho": "morpho-blue-vaults",
    "morpho-blue": "morpho-blue-vaults",
    "metamorpho": "morpho-blue-vaults",
    "spark": "spark",
    "spark-protocol": "spark",
    "spark-lending": "spark-lend",
    "spark-lend": "spark-lend",
    "sky-lending": "bakerdao",
    "lido": "lido",
    "rocket-pool": "rocketpool",
    "rocketpool": "rocketpool",
    "ether.fi": "etherfi",
    "ether-fi": "etherfi",
    "etherfi": "etherfi",
    "frax": "frax-sfrxeth",
    "frax-ether": "frax-sfrxeth",
    "ethena": "ethena-susde",
    # Liquid staking + restaking that DefiLlama users frequently name in
    # natural language. Enso indexes each under its own slug — add the
    # bare protocol-name aliases so "Stake X with Stader" / "with Kelp"
    # / "with Swell" resolves without an explicit position_token.
    "stader": "stader-ethx",
    "stader-labs": "stader-ethx",
    "stader-ethx": "stader-ethx",
    "kelp": "kelp-rseth",
    "kelp-dao": "kelp-rseth",
    "swell": "swell-rsweth",
    "swelleth": "swell-rsweth",
    "swell-network": "swell-rsweth",
    "renzo": "renzo-ezeth",
    "renzo-protocol": "renzo-ezeth",
    "puffer": "puffer-pufeth",
    "puffer-finance": "puffer-pufeth",
    "mantle-staked-eth": "mantle-staked-eth",
    "mantle": "mantle-staked-eth",
    "pendle": "pendle-pt",
    "stargate": "stargate",
    "moonwell": "moonwell",
    "gmx": "gmx-v2",
    "velodrome": "velodrome-v2",
    "velodrome-v2": "velodrome-v2",
    "beefy": "beefy",
    "beefy-clm": "beefy-clm",
    "beefy-finance": "beefy",
    "ichi": "ichi-vaults",
    "ichi-vaults": "ichi-vaults",
    "steer": "steer",
    "gamma": "gamma",
    "arrakis": "arrakis",
    "tokemak": "tokemak-autoeth",
    "aerodrome": "aerodrome-v1",
    "aerodrome-slipstream": "aerodrome-slipstream",
    "uniswap": "uniswap-v3",
    "uniswap-v3": "uniswap-v3",
    "uniswap-v4": "uniswap-v4",
    "pancakeswap": "pancakeswap-v3",
    "pancakeswap-v3": "pancakeswap-v3",
}


def normalize_protocol(slug: str) -> str:
    return _protocol_alias.get(slug.lower(), slug.lower())


def _headers() -> dict[str, str]:
    if not settings.enso_api_key:
        return {}
    return {"X-API-KEY": settings.enso_api_key}


async def _query_tokens(
    chain_id: int, protocol_slug: str, underlying: str
) -> list[dict[str, Any]]:
    await _pace()
    params = {
        "chainId": chain_id,
        "protocolSlug": protocol_slug,
        "underlyingTokens": underlying,
    }
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.get(f"{_BASE}/tokens", params=params, headers=_headers())
        r.raise_for_status()
        body = r.json()
        return body.get("data", [])


async def _query_tokens_no_underlying(
    chain_id: int, protocol_slug: str
) -> list[dict[str, Any]]:
    await _pace()
    params = {"chainId": chain_id, "protocolSlug": protocol_slug, "perPage": 1000}
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(f"{_BASE}/tokens", params=params, headers=_headers())
        r.raise_for_status()
        body = r.json()
        return body.get("data", [])


def _build_position(raw: dict[str, Any]) -> EnsoPosition:
    return EnsoPosition(
        chain_id=int(raw["chainId"]),
        protocol_slug=raw["protocol"],
        position_address=raw["address"],
        decimals=int(raw.get("decimals", 18)),
        underlying_addrs=tuple(
            (u.get("address") or "").lower() for u in raw.get("underlyingTokens", [])
        ),
        apy=raw.get("apy"),
        apy_base=raw.get("apyBase"),
        apy_reward=raw.get("apyReward"),
        tvl=raw.get("tvl"),
        primary_address=raw.get("primaryAddress") or raw["address"],
        deposit_type=raw.get("depositType", "SingleToken"),
        redeem_type=raw.get("redeemType", "SingleToken"),
        raw=raw,
    )


async def resolve_position(
    *, chain_id: int, protocol_slug: str, underlying_addr: str
) -> EnsoPosition | None:
    """Return the Enso position token for (chain, protocol, underlying).

    Tries exact `underlyingTokens` filter first, then falls back to a
    chain-wide protocol scan and matches by underlying address (covers
    multi-token LPs where the filter is too strict).
    """
    slug = normalize_protocol(protocol_slug)
    key = (chain_id, slug, underlying_addr.lower())
    now = time.monotonic()
    async with _cache_lock:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < _CACHE_TTL_S:
            return hit[1]

    found: EnsoPosition | None = None
    try:
        rows = await _query_tokens(chain_id, slug, underlying_addr)
        if rows:
            best = max(rows, key=lambda t: t.get("tvl") or 0)
            found = _build_position(best)
        else:
            # Some pools (Curve, Balancer multi-asset) need a full scan; the
            # underlying-filter endpoint can miss them. Scan the chain/protocol
            # and match underlying in-memory.
            rows = await _query_tokens_no_underlying(chain_id, slug)
            matches: list[dict[str, Any]] = []
            target = underlying_addr.lower()
            for t in rows:
                under = [
                    (u.get("address") or "").lower() for u in t.get("underlyingTokens", [])
                ]
                if target in under:
                    matches.append(t)
            if matches:
                best = max(matches, key=lambda t: t.get("tvl") or 0)
                found = _build_position(best)
    except httpx.HTTPError:
        found = None

    async with _cache_lock:
        _cache[key] = (time.monotonic(), found)
    return found


async def list_positions(
    *, chain_id: int, protocol_slug: str
) -> list[EnsoPosition]:
    slug = normalize_protocol(protocol_slug)
    rows = await _query_tokens_no_underlying(chain_id, slug)
    return [_build_position(r) for r in rows]


# Re-exported chain ids for adapters.
ENSO_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "mainnet": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "bsc": 56,
    "binance": 56,
    "linea": 59144,
    "zksync": 324,
    "scroll": 534352,
    "gnosis": 100,
    "sonic": 146,
    "soneium": 1868,
    "plasma": 9745,
    "ink": 57073,
}
