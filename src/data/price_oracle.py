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


# ---------------------------------------------------------------------------
# V7-044 cleanup — sync cache-only readers for detector hot paths.
#
# The intent-detection regex layer in ``simple_runtime.py`` and the USD↔native
# converter in ``execute_pool_position.py`` are synchronous request-time code
# that cannot ``await`` the oracle without a major refactor. They previously
# carried hardcoded fallback dicts (``WETH=2300`` / ``WBTC=80000``). Those
# hardcodes are removed in favor of these helpers, which read the same
# module-global cache populated by the async ``fetch_price_usd`` path.
#
# Behaviour:
#   - Cache hit (fresh OR stale) → returns the cached float.
#   - Cache miss → returns ``None`` so the caller can either fail-soft (USD
#     conversion skipped, native amount preserved) or pass the raw amount
#     through to the downstream async tool which re-prices via the oracle.
#
# We deliberately do NOT trigger an HTTP fetch from a sync caller (no
# ``asyncio.run`` — detectors run inside the live async event loop).
# ---------------------------------------------------------------------------

# Canonical (chain_slug, token_address) lookup keyed by upper-case symbol.
# Matches the EVM/Solana primary deployment for each token. Used solely to
# resolve a symbol like "WETH" to the cache key the async oracle populates.
_SYMBOL_PRICE_LOOKUP: dict[str, tuple[str, str]] = {
    "ETH":   ("ethereum",  "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"),
    "WETH":  ("ethereum",  "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"),
    "STETH": ("ethereum",  "0xae7ab96520de3a18e5e111b5eaab095312d7fe84"),
    "WSTETH":("ethereum",  "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"),
    "WEETH": ("ethereum",  "0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee"),
    "BTC":   ("ethereum",  "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"),
    "WBTC":  ("ethereum",  "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"),
    "CBBTC": ("base",      "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"),
    "BTC.B": ("avalanche", "0x152b9d0fdc40c096757f570a51e494bd4b943e50"),
    "BNB":   ("bsc",       "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"),
    "WBNB":  ("bsc",       "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"),
    "MATIC": ("polygon",   "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270"),
    "WMATIC":("polygon",   "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270"),
    "POL":   ("polygon",   "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270"),
    "AVAX":  ("avalanche", "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7"),
    "WAVAX": ("avalanche", "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7"),
    "SOL":   ("solana",    "So11111111111111111111111111111111111111112"),
    "WSOL":  ("solana",    "So11111111111111111111111111111111111111112"),
    "ARB":   ("arbitrum",  "0x912ce59144191c1204e64559fe8253a0e49e6548"),
    "OP":    ("optimism",  "0x4200000000000000000000000000000000000042"),
    "AERO":  ("base",      "0x940181a94a35a4569e4529a3cdfb74e38fd98631"),
}

# Stable-coin pegs: returned by the sync reader as $1.00 without an oracle
# round-trip (DefiLlama lists these but the network hop is wasted work for
# a known peg). SUSDE / SUSDS use 1.05 as their fixed conservative peg.
_STABLE_PEG: dict[str, float] = {
    "USDC": 1.0, "USDT": 1.0, "DAI": 1.0, "FRAX": 1.0, "USDE": 1.0,
    "GHO": 1.0, "PYUSD": 1.0, "TUSD": 1.0, "BUSD": 1.0, "FDUSD": 1.0,
    "MIM": 1.0, "MKUSD": 1.0, "CRVUSD": 1.0, "USDS": 1.0,
    "SUSDE": 1.05, "SUSDS": 1.05,
}


def get_cached_price_usd_sync(symbol: str) -> Optional[float]:
    """Cache-only USD price lookup for sync detector hot paths.

    Reads the module-global cache populated by ``fetch_price_usd``. Never
    triggers HTTP; never blocks. Returns ``None`` when the symbol is unknown
    or the cache has no entry — the caller is expected to either skip the
    USD conversion or let a downstream async stage re-price.

    Stablecoins return their fixed peg (``$1.00`` / ``$1.05`` for s-staked
    variants) without touching the cache.
    """
    if not symbol:
        return None
    sym = symbol.upper()
    peg = _STABLE_PEG.get(sym)
    if peg is not None:
        return peg
    lookup = _SYMBOL_PRICE_LOOKUP.get(sym)
    if lookup is None:
        return None
    chain, addr = lookup
    key = (chain.lower(), addr.lower())
    hit = _cache.get(key)
    if hit is None:
        return None
    return hit[0]


async def hydrate_price_cache(symbol: str, http_session: Any) -> Optional[float]:
    """Force-populate the cache for ``symbol`` via the live oracle.

    Called by async pre-detector warm-up paths (e.g. simple_runtime's main
    request handler) so that subsequent sync ``get_cached_price_usd_sync``
    lookups inside detectors return a fresh price.
    """
    if not symbol:
        return None
    sym = symbol.upper()
    lookup = _SYMBOL_PRICE_LOOKUP.get(sym)
    if lookup is None:
        return None
    chain, addr = lookup
    return await fetch_price_usd(chain, addr, http_session)
