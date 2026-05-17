"""Live USD price oracle backed by DefiLlama /prices/current with 60s TTL cache.

V7-044: Kill hardcoded WETH=2300 / WBTC=80000 fallback dicts scattered through
V3 NFT adapter and elsewhere. Single source of truth for spot USD prices,
network-friendly via a per-(chain, addr) in-memory cache.

Endpoint: GET https://coins.llama.fi/prices/current/{chain}:{addr}
  → {"coins": {"{chain}:{addr}": {"price": <float>, "symbol": "...", ...}}}

Cache semantics:
  - Hit (<60s old) → returns cached price, no HTTP
  - Miss / expired → HTTP fetch, cache on success
  - HTTP non-200 / timeout / parse failure → stale-cache fallback if present,
    else None. We NEVER raise — callers can fall back to their own defaults.

The cache is module-global (process-wide). Tests use ``_clear_cache_for_tests``.
"""
from __future__ import annotations

import asyncio
from time import time
from typing import Any, Optional

DEFILLAMA_BASE = "https://coins.llama.fi"
PRICE_CACHE_SECONDS = 60.0

# (chain_lower, addr_lower) -> (price_usd, fetched_at_epoch)
_cache: dict[tuple[str, str], tuple[float, float]] = {}


async def fetch_price_usd(
    chain: str,
    addr: str,
    http_session: Any,
    *,
    timeout: float = 5.0,
) -> Optional[float]:
    """Return spot USD price for an EVM/Solana token via DefiLlama.

    Args:
        chain: DefiLlama chain slug (e.g. ``"ethereum"``, ``"arbitrum"``,
            ``"base"``, ``"solana"``). Case-insensitive.
        addr: Token contract address (EVM 0x... or Solana mint). Case-insensitive.
        http_session: aiohttp.ClientSession or any object exposing an
            ``async with .get(url, timeout=...)`` context manager that yields
            a response with ``.status`` and ``await .json()``.
        timeout: Per-request timeout in seconds. Default 5.0.

    Returns:
        ``float`` USD price on success or stale-cache fallback, ``None``
        when there is no usable value (no cache + fetch failed/missing).
    """
    key = (chain.lower(), addr.lower())
    now = time()
    hit = _cache.get(key)
    if hit and now - hit[1] < PRICE_CACHE_SECONDS:
        return hit[0]

    url = f"{DEFILLAMA_BASE}/prices/current/{chain.lower()}:{addr.lower()}"
    try:
        async with http_session.get(url, timeout=timeout) as resp:
            status = getattr(resp, "status", 0)
            if status != 200:
                return hit[0] if hit else None
            body = await resp.json()
    except (asyncio.TimeoutError, Exception):
        return hit[0] if hit else None

    coins = body.get("coins", {}) if isinstance(body, dict) else {}
    coin_key = f"{chain.lower()}:{addr.lower()}"
    entry = coins.get(coin_key) if isinstance(coins, dict) else None
    price = entry.get("price") if isinstance(entry, dict) else None
    if isinstance(price, (int, float)) and price > 0:
        _cache[key] = (float(price), now)
        return float(price)
    return hit[0] if hit else None


def _clear_cache_for_tests() -> None:
    """Test helper — wipe the module-global cache. Do not call in prod code."""
    _cache.clear()
